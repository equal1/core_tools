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
from core_tools.data.sqdl.export.data_export import (
    export_data, update_metadata,
    get_export_path, check_for_metadata_changes,
)
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
        self.project = cfg["project"]
        self.scope = cfg.get("scope")

        self.no_action_count = 0
        self.loop_count = 0

        self.process = psutil.Process()
        self.active_action: ExportAction | None = None

    def poll(self) -> bool:
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
        return done_work

    def export_one(self):
        """
        Core exporter loop. Identifies which dataset to handle, exports it to the
        local filesystem, then queues the sQDL Uploader to move these exported files
        to an sQDL backend.

        Returns:
            Whether the exporter is busy with a running measurement.

        Raises:
            Exception: Only unforseen or fatal error-cases.
        """
        self.timer = Timer()
        self.timer.time('query actions')

        ds = None
        try:
            action, is_busy = self.get_action()
            if not action:
                return is_busy

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

            if not action.completed:
                self.handle_incomplete_dataset(
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

            # Note: Tick off failed export as synced, so that it does not get stuck
            #  on one particular entry. When new data is added, the exporter will
            #  try again.
            export.set_export_synchronized(
                action=action,
                name=ds.exp_name,
                rating=ds.starred
            )

        finally:
            if ds is not None:
                try:
                    ds.close()
                except Exception:
                    pass

        return True

    def handle_incomplete_dataset(self, action, start_time, run_timestamp):
        duration = int(time.perf_counter() - start_time)
        wait_time = duration + self.get_wait_time_not_completed(run_timestamp)
        action.resume_after = datetime.now() + timedelta(seconds=wait_time)
        self.active_action = action

    def parse_exception(
            self,
            message: str,
            action: ExportAction
    ) -> int:
        """
        Parse exception message to extract error code.

        code 99: unspecified error
        code > 100: known error and not recoverable, e.g. corrupt dataset.

        Args:
            message: Raised error message.
            action: The current export action being handled.

        Returns:
            Identified error code.

        Raises:
            Exception: Any unidentified or fatal error-cases.
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

    def get_action(self) -> tuple[ExportAction | None, bool]:
        """
        Get the next ExportAction object to handle.

        Objects are retrieved/created with the following priority:
        1) Active action: Continue handling the current long-running measurement.
        2) Mutated data: Export data that has recently been modified, including:
            - Currently running measurements
            - Recently finished measurements
            - Next item in the backlog (ordered by UUID)
        3) Mutated meta-data: Export any pending name- or rating-changes.
        4) Expired exports: Re-export any measurements that have been successfully
            exported, but that have been left incomplete for extended period without
            updates.

        Returns:
            action: Next export action to perform, if any exist.
            is_busy: Value to distinguish between throttling export rates and having
                nothing to export.
        """
        export_entry = export.get_data_for_export(self.project)
        if export_entry is not None:
            if self.active_action is not None:
                if (
                    export_entry["uuid"] == self.active_action.uuid
                    and
                    datetime.now() < self.active_action.resume_after
                ):
                    return None, True

            # changes can be false if no local export exists yet
            changed_rating, changed_name = self.check_for_export_files(export_entry)
            action = ExportAction(
                uuid=export_entry["uuid"],
                data_changed=not export_entry["data_synchronized"],
                completed=export_entry["completed"],
                update_name=changed_name,
                update_star=changed_rating,
                data_modify_count=export_entry["data_update_count"],
                resume_after=None,
            )
            return action, True

        action = export.get_expired_export_action(
            self.get_measurement_expiration_threshold()
        )
        if action is not None:
            logger.info(
                f'Export raw data of expired incomplete measurement {action.uuid}'
            )
            return action, True

        return None, False

    def check_for_export_files(self, export_entry: dict[str, Any]):
        export_uuid = export_entry["uuid"]

        # get local path
        export_path, export_json = get_export_path(
            self.export_path,
            export_entry["project"],
            export_entry["start_time"],
            f"{export_uuid}"
        )
        logger.info(f"checking for previous export: path = {export_path}")

        if not (export_path.exists() and export_json.exists()):
            logger.warning("no previous export found")
            return False, False

        return check_for_metadata_changes(
            export_json,
            export_entry["exp_name"],
            export_entry["starred"]
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

    def get_measurement_expiration_threshold(self):
        return datetime.now() - timedelta(days=1)

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

    def validate_scope(self, ds: DataSet) -> str:
        """
        Retrieve scope value for measurement.
        If no scope is defined in the core-tools database, check if the project
        name matches the current config, and extract scope from there.

        Args:
            ds: Measurement DataSet object.

        Returns:
            Scope name.

        Raises:
            Exception: If no scope is found.
        """
        scope = ds.scope
        if scope is None:
            logger.info(
                f"No scope value found for measurement with UID {ds.exp_uuid}, "
                "checking local config for a matching project name with scope."
            )
            if ds.project == self.project:
                # Only handle (expired) exports that belong to the current project.
                scope = self.scope

        if scope is None:
            raise Exception(
                f"No scope for measurement with UID {ds.exp_uuid}"
            )
        return scope

    def export_measurement(self, measurement: DataSet, is_complete: bool
                           ) -> tuple[SqdlUpdate, str]:
        scope = self.validate_scope(measurement)
        updates = SqdlUpdate(measurement.exp_uuid, scope, raw_final=is_complete)
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

        if updates.upload_dataset or updates.upload_raw_data:
            # note: upload_raw_data makes export run the generation of previews any
            #  time new data is being exported -> could be resource intensive
            generate_previews(dsx, ds_path, var_descr, self.timer)

        update_metadata(ds_path, measurement.exp_uuid)

        return updates, ds_path
