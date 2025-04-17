import gc
import json
import logging
import psutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from pathlib import Path

import numpy as np
import psycopg2

from core_tools.data.ds.data_set import load_by_uuid, data_set as DataSet
from core_tools.data.utils.timer import Timer
from core_tools.data.SQL.SQL_connection_mgr import (
    SQL_database_manager as DatabaseManager
)
from core_tools.data.sqdl.export.data_export import export_data
from core_tools.data.sqdl.export.data_preview import generate_previews
from core_tools.data.sqdl.model import export
from core_tools.data.sqdl.model.export import ExportAction

import sqdl_uploader


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
    def __init__(self, cfg: dict[str, Any]):
        base_path = cfg.get('sqdl_sync.base_path', "~/.sqdl")
        self.export_path = f"{base_path}/export"
        self.scope_config_for_project = {cfg["project"]: cfg.get("scope")}

        self.no_action_count = 0
        self.loop_count = 0

        self.process = psutil.Process()
        self.enqueued_action: ExportAction | None = None

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
            logger.info(
                f"GC unreachable: {unreachable} "
                f"counts:{gc.get_count()} {gc.get_freeze_count()}"
            )
            logger.info(f"MEM: {self.process.memory_info()}")

        if self.loop_count % 1_000 == 0:
            logger.info("Close database connection to free memory")
            unreachable = gc.collect()
            logger.info(
                f"GC2 unreachable: {unreachable} "
                f"counts:{gc.get_count()} {gc.get_freeze_count()}"
            )
            logger.info(f"MEM2: {self.process.memory_info()}")

    def export_one(self):
        """
        """
        self.timer = Timer()
        self.timer.time('query actions')

        ds = None
        try:
            if not self.continue_enqueued_action():
                return True

            action = self.get_action()
            if not action:
                return False

            start_time = time.perf_counter()
            self.timer.time('load')
            ds: DataSet = load_by_uuid(action.uuid)
            logger.info(
                f'Exporting {action.uuid}, {ds.run_timestamp}, '
                f'{ds.set_up}, {ds.project}'
            )
            action.completed = (
                action.completed
                or self.measurement_is_completed(ds)
                or ds.run_timestamp < self.measurement_expiration_time
            )
            sqdl_update, ds_path = self.export_measurement(ds, action.completed)

            sqdl_update.update_star |= action.update_star
            sqdl_update.update_name |= action.update_name

            self.add_sqdl_update(sqdl_update, ds_path)

            export.set_exported(
                ds,
                ds_path,
                is_complete=action.completed
            )

            self.timer.log_times()
            logger.info(f'Exported {action.uuid}')

            data_synced, table_synced = export.set_export_synchronized(
                action=action,
                name=ds.exp_name,
                rating=ds.starred
            )

            if not data_synced:
                logger.info("Measurement data modified during export.")
            if not table_synced:
                logger.info("Measurement name or rating changed during export.")

            if not (action.completed or (data_synced and table_synced)):
                self.handle_modified_export(
                    action, start_time, ds.run_timestamp
                )

        except (psycopg2.Error, psycopg2.Warning):
            logger.error("Database error", exc_info=True)
            time.sleep(2.0)

        except Exception as ex:
            message = str(ex)
            error_code = self.parse_exception(
                message, action
            )

            export.set_export_error(
                action.uuid,
                message,
                error_code
            )

            # -----
            # review todo: yanked from green path, needs validation
            data_synced, table_synced = export.set_export_synchronized(
                action=action,
                name=ds.exp_name,
                rating=ds.starred
            )

            if not data_synced:
                logger.info("Measurement data modified during export.")
            if not table_synced:
                logger.info("Measurement name or rating changed during export.")

            if not (action.completed or (data_synced and table_synced)):
                self.handle_modified_export(
                    action, start_time, ds.run_timestamp
                )
            # -----

        finally:
            if ds is not None:
                try:
                    ds.close()
                except Exception:
                    pass

        return True

    def handle_modified_export(self, action, start_time, run_timestamp):
        duration = int(time.perf_counter() - start_time)
        wait_time = duration + self.get_wait_time_not_completed(run_timestamp)
        action.resume_after = datetime.now() + timedelta(seconds=wait_time)
        self.enqueued_action = action

    def parse_exception(
            self,
            message: str,
            action: ExportAction
    ) -> int:
        """
        Parse exception message to extract error code and establish retry delay.

        code 10 - 49: known error and (possibly) recoverable
        code 50 - 90: known error and retry
        code 99: unspecified error
        code > 100: known error and not recoverable, e.g. corrupt dataset.

        :param message: Raised error message.
        :param action: The current export action being handled.
        :returns: Identified error code.
        """
        error_code = 99

        if message.startswith("No data in dataset"):
            # NOTE: new action will be created when data is written
            logger.warning(message)
            error_code = 101

        elif message.startswith("m_param with id"):
            # NOTE: new action will be created when data is written
            logger.warning(message)
            error_code = 102
        else:
            logger.error(
                f'Failed to export {action.uuid} with error: {message}',
                exc_info=True,
            )
            raise

        return error_code

    def continue_enqueued_action(self) -> bool:
        """
        Determine whether to continue the export of an enqueued action, if it
        exists.

        :returns: Confirmation to resume action.
        """
        if (self.enqueued_action is None
                or self.enqueued_action.resume_after < datetime.now()):
            return True

        # resume early if the measurement is finished
        is_complete = export.get_measurement_completed(self.enqueued_action.uuid)
        assert_message = "Enqueued action UID no longer exists in database"
        assert is_complete is not None, assert_message

        if is_complete:
            self.enqueued_action.completed = True
            return True

        return False

    def get_action(self) -> ExportAction | None:
        """
        Get the next ExportAction object to handle.

        Objects are retrieved/created with the following priority:
        1) Enqueued actions: Continue handling the current long-running measurement.
        2) Mutated data: Export data that has recently been modified, including:
            - Currently running measurements
            - Recently finished measurements
            - Next item in the backlog (ordered by UUID)
        3) Mutated meta-data: Export any pending name- or rating-changes.
        4) Expired exports: Re-export any measurements that have been successfully
            exported, but that have been left incomplete for extended period without
            updates.

        :returns: Next export action to perform, if any exist.
        """
        if self.enqueued_action is not None:
            action = self.enqueued_action
            self.enqueued_action = None
            return action

        export_entry = export.get_data_for_export()
        if export_entry is not None:
            # changes can be false if no local export exists yet
            changed_rating, changed_name = self.check_for_export_files(export_entry)
            return ExportAction(
                uuid=export_entry["uuid"],
                data_changed=not export_entry["data_synchronized"],
                completed=export_entry["completed"],
                update_name=changed_name,
                update_star=changed_rating,
                data_modify_count=export_entry["data_update_count"],
                resume_after=None,
            )

        action = export.get_expired_export_action(
            self.measurement_expiration_time
        )
        if action is not None:
            logger.info(
                f'Export raw data of expired incomplete measurement {action.uuid}'
            )
            return action

        return None

    def check_for_export_files(self, export_entry: dict[str, Any]):
        # get local path
        file_path = Path(
            self.export_path,
            export_entry["project"],
            export_entry["start_time"].strftime("%Y-%m-%d"),
            f"{export_entry["uuid"]}"
        ).expanduser()

        logger.info(f"checking for previous export: path = {file_path}")

        if not file_path.exists():
            logger.warning("no previous export found")
            return False, False

        with open(Path(file_path, f"{export_entry["uuid"]}.json")) as f:
            local_data = json.load(f)

        name_changed = export_entry["exp_name"] != local_data.get("name", "")
        rating_changed = export_entry["starred"] != local_data.get("starred", False)

        return name_changed, rating_changed

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
        if sqdl_update.upload_dataset or sqdl_update.upload_raw_data:
            sqdl_uploader.enqueue_upload_task(
                scope=sqdl_update.scope,
                uid=sqdl_update.uuid,
                path=ds_path,
                is_finished=sqdl_update.raw_final,
            )

        if sqdl_update.update_star:
            sqdl_uploader.enqueue_update_task_name(
                scope=sqdl_update.scope,
                uid=sqdl_update.uuid,
                path=ds_path
            )

        if sqdl_update.update_name:
            sqdl_uploader.enqueue_update_task_rating(
                scope=sqdl_update.scope,
                uid=sqdl_update.uuid,
                path=ds_path
            )

    @property
    def measurement_expiration_time(self):
        return datetime.now() - timedelta(days=3)

    def measurement_is_completed(self, measurement):
        if measurement.completed:
            return True
        for m_param in measurement:
            for name, descr in m_param:
                if descr.written() != np.prod(descr.shape):
                    logger.info(
                        f'Data for {name} not complete: '
                        f'{descr.written()} != prod({descr.shape})'
                    )
                    return False
        return True

    def get_scope(self, uid: int) -> str:
        """
        Retrieve scope value for measurement.
        If no scope is defined in the core-tools database, check if the project
        name matches the current config, and extract scope from there.

        :param uid: Measurement UID.
        :returns: Scope name.
        :raises Exception: If no scope is found.
        """
        response = export.get_measurement_scope(uid)
        assert response is not None, f"Unreachable: No measurement with UID '{uid}'"

        scope = response["scope"]
        if scope is None:
            logger.warning(
                f"No scope value found for measurement with ID {uid}, "
                "checking local config for a matching project name with scope."
            )
            project_name = response["project"]
            scope = self.scope_config_for_project.get(project_name)

        if scope is None:
            raise Exception(f"No scope for measurement with ID '{uid}'")
        return scope

    def export_measurement(self, measurement: DataSet, is_complete: bool
                           ) -> tuple[SqdlUpdate, str]:
        scope = self.get_scope(int(measurement.exp_uuid))
        updates = SqdlUpdate(measurement.exp_uuid, scope, raw_final=is_complete)
        try:
            # review todo: always doing export raw -> updates.upload_raw always true
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
