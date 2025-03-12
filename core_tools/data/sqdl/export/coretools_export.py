import gc
import logging
import psutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict

import numpy as np
import psycopg2
from psycopg2._psycopg import connection as Connection

from core_tools.data.ds.data_set import load_by_uuid
from core_tools.data.utils.timer import Timer
from core_tools.data.sqdl.export.data_export import export_data
from core_tools.data.sqdl.export.data_preview import generate_previews
from core_tools.data.sqdl.model import core, task_queue, export
from core_tools.data.sqdl.model.task_queue import DatasetInfo
from core_tools.data.sqdl.model.export import ExportAction


logger = logging.getLogger(__name__)


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
    def __init__(self, cfg: Dict, conn: Connection):
        self.export_path = "{}/export".format(cfg.get('sqdl_sync.base_path', "~/.sqdl"))
        self.connection = conn

        if cfg.get("sqdl_sync.retry_failed_exports", default=False):
            self.retry_failed_exports()

        self.setup_name_corrections = cfg.get('sqdl_sync.setup_name_corrections', {})

        self.no_action_count = 0
        self.loop_count = 0

        self.process = psutil.Process()

    def poll(self) -> None:
        self.loop_count += 1
        done_work = self.export_one()
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

    def export_one(self):
        """
        """
        self.timer = Timer()
        self.timer.time('query actions')

        # NOTE:
        # New measurement locally first adds the dataset to the global_measurmeent_overview,
        # but the sync script first adds the measurement parameters and then creates the entry
        # in global_measurement_overview.
        # So, an update of the data may be written before the measurement with UUID is added to the
        # global measurement overview.

        action = self.get_action()
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

            self.add_sqdl_update(sqdl_update, ds_path)
            # self.set_exported(ds, ds_path, action.completed)
            export.set_exported(self.connection, ds, ds_path, is_complete=action.completed)

            if action.id is not None:
                # id is None for expired measurements

                # deleted = self.delete_export_action(action)
                deleted = export.delete_export_action(self.connection, action)
                if not deleted and not action.completed:
                    # action is not deleted when dataset has been modified during export
                    duration = int(time.perf_counter() - start_time)
                    wait_time = duration + self.get_wait_time_not_completed(ds.run_timestamp)
                    # self.set_resume_after(action, wait_time)
                    export.set_resume_after(self.connection, action, wait_time)

            self.timer.log_times()

            logger.info(f'Exported {uuid}')

        except (psycopg2.Error, psycopg2.Warning):
            logger.error("Database error", exc_info=True)
            time.sleep(2.0)
            try:
                self.connection.close()
            except Exception:
                pass

        except Exception as ex:
            message = str(ex)
            sleep_time, error_code, retry_after = self.parse_exception(message, action)

            # self.set_export_error(uuid, ex, error_code)
            export.set_export_error(self.connection, uuid, message, error_code)

            if action.id is not None:
                # id is None for expired measurements
                if retry_after is not None:
                    # self.increment_fail_count(action)
                    export.increment_fail_count(self.connection, action)
                    # self.set_resume_after(action, retry_after + sleep_time)
                    export.set_resume_after(self.connection, action, retry_after + sleep_time)
                else:
                    # self.delete_export_action(action)
                    export.delete_export_action(self.connection, action)

            time.sleep(sleep_time)

        finally:
            if ds is not None:
                try:
                    ds.close()
                except Exception:
                    pass

        return True

    def parse_exception(self, message: str, action: ExportAction) -> Tuple[float, int, float]:
        """
        Parse exception message to extract error code and establish retry delay.

        code 10 - 49: known error and (possibly) recoverable
        code 50 - 90: known error and retry
        code 99: unspecified error
        code > 100: know error and not recoverable, e.g. corrupt dataset.
        """
        sleep_time = 0.001
        error_code = 99
        retry_after = None

        if message.startswith("No scope for project"):
            logger.warning(message)
            error_code = 11
        elif message.startswith("Failed reading/writing file(s)"):
            logger.warning(message)
            error_code = 50
            sleep_time = 0.5
            if action.fail_count < 30:
                retry_after = 1.0 * action.fail_count
        elif message.startswith("No data in dataset"):
            # NOTE: new action will be created when data is written
            logger.warning(message)
            error_code = 101
        elif message.startswith("m_param with id"):
            # NOTE: new action will be created when data is written
            logger.warning(message)
            error_code = 102
        elif message.startswith("Dataset ") and 'too big' in message:
            logger.warning(message)
            error_code = 103
        elif "does not exist in the local/remote database" in message:
            # The synchronization process has not yet finished the sync.
            logger.warning(message)
            error_code = 104
        else:
            logger.error(f'Failed to export {action.uuid}', exc_info=True)
            self.connection.abort()
            sleep_time = 0.5
            if action.fail_count < 10:
                retry_after = 5.0 + 2.0 * action.fail_count

        return sleep_time, error_code, retry_after

    def get_action(self) -> Optional[ExportAction]:
        action = export.get_export_action(self.connection)
        # action = self.get_export_action()
        if action is not None:
            return action

        action = export.get_expired_export_action(self.connection, self.measurement_expiration_time)
        # action = self.get_expired_measurement_action()
        if action is not None:
            logger.info(f'Export raw data of expired incomplete measurement {action.uuid}')
        return action

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

    def get_wait_time_not_completed(self, start_timestamp: datetime) -> int:
        now = datetime.now()
        measurement_duration = now - start_timestamp
        if measurement_duration < timedelta(seconds=10):
            return 0.5
        elif measurement_duration < timedelta(seconds=30):
            return 2
        else:
            return 4

    def add_sqdl_update(self, sqdl_update: SqdlUpdate, ds_path: str) -> None:
        ds_info = DatasetInfo(
            scope=sqdl_update.scope,
            uid=sqdl_update.uuid,
            path=ds_path
        )

        if sqdl_update.upload_dataset or sqdl_update.upload_raw_data:
            task_queue.update_dataset(self.connection, dsi=ds_info, is_finished=sqdl_update.raw_final)
        if sqdl_update.update_star:
            task_queue.update_rating(self.connection, dsi=ds_info)
        if sqdl_update.update_name:
            task_queue.update_name(self.connection, dsi=ds_info)

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

    def get_scope(self, coretools_uid: int) -> str:
        scope = core.get_scope(self.connection, coretools_uid)
        if scope is None:
            raise Exception(f"No scope for measurement with ID '{coretools_uid}'")
        return scope

    def fix_setup_name(self, setup):
        return self.setup_name_corrections.get(setup, setup)

    def export_measurement(self, measurement, action: ExportAction) -> Tuple[SqdlUpdate, str]:
        scope = self.get_scope(int(measurement.exp_uuid))
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

    def retry_failed_exports(self):
        records = export.get_failed_exports(self.connection)

        if len(records) == 0:
            return None

        logger.warning("Inserting {} datasets for export retry.".format(len(records)))
        for uuid, is_complete in records:
            export.set_retry_export(self.connection, uuid, is_complete)
