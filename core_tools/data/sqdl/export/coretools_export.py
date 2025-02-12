import gc
import logging
import psutil
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict

import numpy as np

import psycopg2
from psycopg2._psycopg import connection as Connection

import core_tools as ct
from core_tools.startup.config import get_configuration
from core_tools.data.ds.data_set import load_by_uuid

from core_tools.data.sqdl.export.psql_commands import SqlConnection
from core_tools.data.utils.timer import Timer
from core_tools.data.sqdl.export.data_export import export_data
from core_tools.data.sqdl.export.data_preview import generate_previews
# from core_tools.data.sqdl.uploader_db import UploaderDb

from core_tools.data.sqdl.model.task_queue import TaskQueueOperations, DatasetInfo
# from core_tools.data.sqdl.uploader_task_queue import UploaderTaskQueue, DatasetLocator

logger = logging.getLogger(__name__)


@dataclass
class ExportAction:
    uuid: int
    id: Optional[int] = None
    modify_count: int = 0
    new_measurement: bool = False
    data_changed: bool = False
    completed: bool = False
    update_star: bool = False
    update_name: bool = False
    fail_count: int = 0
    resume_after: datetime = None


@dataclass
class SqdlUpdate:
    uuid: int
    scope: str
    upload_dataset: bool = False
    upload_raw_data: bool = False
    update_star: bool = False
    update_name: bool = False
    raw_final: bool = False


class Exporter:

    def __init__(self, cfg: Dict):
        self.cfg = cfg
        self.export_path = cfg.get('export.path')
        self.inter_ds_delay = float(cfg.get('export.delay'))
        self.connection = SqlConnection()
        # self.uploader_db = UploaderDb(cfg)
        # self.connection = self.uploader_db.engine.connect()

        # self.uploader_queue = UploaderTaskQueue(self.uploader_db)
        self.uploader = TaskQueueOperations()

        self.scopes = cfg.get('export.scopes', {})
        self.setup_name_corrections = cfg.get('export.setup_name_corrections', {})

        self.no_action_count = 0
        self.loop_count = 0

        self.process = psutil.Process()

    def poll(self, conn: Connection) -> None:
        try:
            self.loop_count += 1
            done_work = self.export_one(conn)
            if not done_work:
                if self.no_action_count == 0:
                    self.timer.log_times()
                if (self.no_action_count % 100) == 0:
                    logger.info('Nothing to export')
                self.no_action_count += 1
            else:
                self.no_action_count = 0
                unreachable = gc.collect()
                logger.info(f"GC unreachable: {unreachable} counts:{gc.get_count()} {gc.get_freeze_count()}")
                logger.info(f"MEM: {self.process.memory_info()}")

            if self.loop_count % 1_000 == 0:
                logger.info("Close database connection to free memory")
                self.connection.close()
                unreachable = gc.collect()
                logger.info(f"GC2 unreachable: {unreachable} counts:{gc.get_count()} {gc.get_freeze_count()}")
                logger.info(f"MEM2: {self.process.memory_info()}")
        except (psycopg2.Error, psycopg2.Warning):
            logger.error("Database error", exc_info=True)
        except Exception:
            logger.error("Unanticipated error", exc_info=True)

    def export_one(self, conn: Connection):
        self.timer = Timer()
        self.timer.time('query actions')

        # NOTE:
        # New measurement locally first adds the dataset to the global_measurmeent_overview,
        # but the sync script first adds the measurement parameters and then creates the entry
        # in global_measurement_overview.
        # So, an update of the data may be written before the measurement with UUID is added to the
        # global measurement overview.
        action = self.get_export_action()
        if not action:
            action = self.get_expired_measurement_action()
            if action:
                logger.info(f'Export raw data of expired incomplete measurement {action.uuid}')
        if not action:
            return False

        ds = None
        try:
            start_time = time.perf_counter()
            uuid = action.uuid
            self.timer.time('load')
            ds = load_by_uuid(uuid)
            logger.info(f'Exporting {action.uuid}, {ds.run_timestamp}, {ds.set_up}, {ds.project}')
            action.completed = (
                action.completed
                or self.measurement_is_completed(ds)
                or ds.run_timestamp < self.measurement_expiration_time
            )
            sqdl_update, ds_path = self.export_measurement(ds, action)
            sqdl_update.update_star |= action.update_star
            sqdl_update.update_name |= action.update_name
            self.add_sqdl_update(conn, sqdl_update, ds_path)
            self.set_exported(ds, ds_path, action.completed)
            if action.id is not None:
                # id is None for expired measurements
                deleted = self.delete_export_action(action)
                if not deleted and not action.completed:
                    # action is not deleted when dataset has been modified during export
                    duration = int(time.perf_counter() - start_time)
                    wait_time = duration + self.get_wait_time_not_completed(ds.run_timestamp)
                    self.set_resume_after(action, wait_time)
            self.timer.log_times()
            self.connection.commit()
            logger.info(f'Exported {uuid}')
            time.sleep(self.inter_ds_delay)

        except (psycopg2.Error, psycopg2.Warning):
            logger.error("Database error", exc_info=True)
            time.sleep(2.0)
            try:
                self.connection.close()
            except Exception:
                pass

        except Exception as ex:
            sleep_time = 0.001
            error_code = 99
            retry_after = None
            msg = str(ex)
            # code 10 - 49: known error and (possibly) recoverable
            # code 50 - 90: known error and retry
            # code 99: unspecified error
            # code > 100: know error and not recoverable, e.g. corrupt dataset.
            if msg.startswith("No scope for project"):
                logger.warning(str(ex))
                error_code = 11
            elif msg.startswith("Failed reading/writing file(s)"):
                logger.warning(str(ex))
                error_code = 50
                retry_after = 5.0
                sleep_time = 0.5
                if action.fail_count < 30:
                    retry_after = 1.0 * action.fail_count
            elif msg.startswith("No data in dataset"):
                # NOTE: new action will be created when data is written
                logger.warning(str(ex))
                error_code = 101
            elif msg.startswith("m_param with id"):
                # NOTE: new action will be created when data is written
                logger.warning(str(ex))
                error_code = 102
            elif msg.startswith("Dataset ") and 'too big' in msg:
                logger.warning(str(ex))
                error_code = 103
            elif "does not exist in the local/remote database" in msg:
                # The synchronization process has not yet finished the sync.
                logger.warning(str(ex))
                error_code = 104
            else:
                logger.error(f'Failed to export {uuid}', exc_info=True)
                self.connection.abort()
                sleep_time = 0.5
                if action.fail_count < 10:
                    retry_after = 5.0 + 2.0 * action.fail_count
            self.set_export_error(uuid, ex, error_code)
            if action.id is not None:
                # id is None for expired measurements
                if retry_after is not None:
                    self.increment_fail_count(action)
                    self.set_resume_after(action, retry_after + sleep_time)
                else:
                    self.delete_export_action(action)
            self.connection.commit()
            time.sleep(sleep_time)

        finally:
            if ds is not None:
                try:
                    ds.close()
                except:
                    pass

        return True

    def get_export_action(self) -> Optional[ExportAction]:
        now = datetime.now()
        action_data = self.connection.execute_query(
            '''
            SELECT * FROM coretools_export_updates
            WHERE resume_after < %(now)s
            ORDER BY uuid LIMIT 1
            ''',
            return_dict=True,
            vars={"now": now},
        )
        if action_data:
            return ExportAction(**action_data[0])
        else:
            return None

    def uuid_exists(self, uuid):
        res = self.connection.execute_query(
            f'''
            SELECT uuid FROM global_measurement_overview WHERE uuid = {uuid}
            '''
        )
        return len(res) > 0 and res[0][0] is not None

    def get_expired_measurement_action(self) -> Optional[ExportAction]:
        data = self.connection.execute_query(
            '''
            SELECT uuid FROM coretools_exported
            WHERE raw_final = False
            AND measurement_start_time < %(expiration_time)s
            AND export_state = 1
            ORDER BY uuid LIMIT 1
            ''',
            vars={'expiration_time': self.measurement_expiration_time},
            return_dict=True
        )
        if not data:
            return None
        else:
            return ExportAction(data[0]['uuid'], completed=True)

    def set_export_error(self, uuid, exception, code=99) -> None:
        if isinstance(exception, Exception):
            error_msg = str(exception)
        else:
            error_msg = f'{type(Exception)}: {str(exception)}'

        self.connection.insert_or_update(
            'coretools_exported',
            {'uuid': uuid},
            {'export_state': code, 'export_errors': error_msg}
        )

    def set_exported(self, measurement, ds_path, action_completed=False) -> None:
        uuid = measurement.exp_uuid
        start_time = measurement.run_timestamp
        raw_final = measurement.completed or action_completed

        self.connection.insert_or_update(
            'coretools_exported',
            {'uuid': uuid},
            {'measurement_start_time': start_time,
             'path': ds_path,
             'export_state': 1,
             'raw_final': raw_final})

    def delete_export_action(self, action: ExportAction) -> bool:
        rowcount = self.connection.execute_statement(
            f'''
            DELETE FROM coretools_export_updates
            WHERE id = {action.id} AND modify_count = {action.modify_count}
            ''')
        return rowcount > 0

    def get_wait_time_not_completed(self, start_timestamp: datetime) -> int:
        now = datetime.now()
        measurement_duration = now - start_timestamp
        if measurement_duration < timedelta(seconds=10):
            return 0.5
        elif measurement_duration < timedelta(seconds=30):
            return 2
        else:
            return 4

    def set_resume_after(self, action: ExportAction, wait_time: int) -> None:
        now = datetime.now()
        resume_after = now + timedelta(seconds=wait_time)

        self.connection.execute_statement(
            f'''
            UPDATE coretools_export_updates
            SET resume_after = %(resume_after)s
            WHERE id = {action.id}
            ''',
            vars={"resume_after": resume_after}
        )

    def increment_fail_count(self, action: ExportAction):
        self.connection.execute_statement(
            f'''
            UPDATE coretools_export_updates
            SET fail_count = fail_count + 1
            WHERE id = {action.id}
            ''',
        )

    def add_sqdl_update(self, conn: Connection, sqdl_update: SqdlUpdate, ds_path: str) -> None:
        # ds_locator = DatasetLocator(sqdl_update.scope, uid=sqdl_update.uuid, path=ds_path)
        ds_info = DatasetInfo(
            scope=sqdl_update.scope,
            uid=sqdl_update.uuid,
            path=ds_path
        )

        with conn:
            c = conn.cursor()
            if sqdl_update.upload_dataset or sqdl_update.upload_raw_data:
                # self.uploader_queue.update_dataset(ds_locator, final=sqdl_update.raw_final)
                self.uploader.update_dataset(c, dsi=ds_info, is_finished=sqdl_update.raw_final)
            if sqdl_update.update_star:
                # self.uploader_queue.update_rating(ds_locator)
                self.uploader.update_rating(c, dsi=ds_info)
            if sqdl_update.update_name:
                # self.uploader_queue.update_name(ds_locator)
                self.uploader.update_name(c, dsi=ds_info)

    @property
    def measurement_expiration_time(self):
        return datetime.now() - timedelta(days=3)

    def measurement_is_completed(self, measurement):
        if measurement.completed:
            return True
        for m_param in measurement:
            for name, descr in m_param:
                if descr.written() != np.prod(descr.shape):
                    logger.info(f'Data for {name} not complete {descr.written()} != prod({descr.shape})')
                    return False
        return True

    def get_scope(self, measurement):
        try:
            scope = self.scopes[measurement.project]
            if isinstance(scope, Mapping):
                scope = scope[measurement.set_up]
            return scope
        except KeyError:
            raise Exception(f"No scope for project '{measurement.project}'")

    def fix_setup_name(self, setup):
        return self.setup_name_corrections.get(setup, setup)

    def export_measurement(self, measurement, action: ExportAction) -> Tuple[SqdlUpdate, str]:
        scope = self.get_scope(measurement)
        measurement.set_up = self.fix_setup_name(measurement.set_up)
        updates = SqdlUpdate(measurement.exp_uuid, scope, raw_final=action.completed)
        try:
            dsx, ds_path, var_descr = export_data(
                measurement,
                scope,
                self.export_path,
                self.timer,
                updates
            )
        except OSError:
            logger.error("Failed reading/writing file(s)", exc_info=True)
            raise Exception("Failed reading/writing file(s)")

        if updates.upload_dataset:
            generate_previews(dsx, ds_path, var_descr, self.timer)

        return updates, ds_path

    def retry_failed_exports(self) -> None:
        data = self.connection.execute_query(
            '''
            SELECT uuid, raw_final FROM coretools_exported
            WHERE export_state BETWEEN 10 AND 100
            ORDER BY uuid
            '''
        )
        if not data:
            return None
        logger.warning(f'Inserting {len(data)} datasets for retry')
        for uuid, raw_final in data:
            self.connection.insert_or_update(
                'coretools_export_updates',
                {'uuid': uuid},
                {'data_changed': True,
                 'completed': raw_final})
            self.connection.commit()


def main(configuration_file: str):
    ct.configure(configuration_file)
    cfg = get_configuration()
    try:
        exporter = Exporter(cfg)
        if cfg.get('export.retry_failed', False):
            exporter.retry_failed_exports()
        exporter.poll()
    except Exception:
        logger.error('Error running exporter', exc_info=True)
        raise
    finally:
        logger.info('Exit application')
