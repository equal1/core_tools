import os
import time
import logging
import datetime

from core_tools.data.SQL.SQL_connection_mgr import SQL_database_manager as DatabaseManager
from core_tools.data.SQL.versioning import get_database_version
from core_tools.data.sqdl.export.coretools_export import Exporter

from sqdl_uploader import SqdlUploader

__database_version__ = "1.1.0"

logger = logging.getLogger(__name__)


# [x] Review SdS: sqdl_writer is not the counterpart of sqdl_reader. sqdl_data_sync?
class SQDLSync():
    """
    Event loop that polls for measurement data to be uploaded to SQDL.
    Expects the core-tools configurations to be initialised (see core-tools/startup/config.py).
    Start the loop using the 'run' method.
    """

    def __init__(self, config):
        # [x] REVIEW SdS: could also use local database SQL_database_manager()
        database = DatabaseManager()

        if not database.local_conn_active:
            # [x] REVIEW SdS: or no database configured?
            raise Exception(
                "Local database setup is a requirement for SQDL Sync, but no local configuration has been found."
            )
        self.validate_version()

        base_path = config.get("sqdl_sync.base_path", "~/.sqdl")
        self.base_path = os.path.expanduser(base_path)
        os.makedirs(self.base_path, exist_ok=True)
        os.makedirs(f"{self.base_path}/export", exist_ok=True)
        # review todo: make sure that uploader files are also created

        self.exporter = Exporter(config)
        self.uploader = SqdlUploader(config)

        self.tick_rate = datetime.timedelta(
            seconds=config.get("sqdl_sync.tick_rate", default=0.1)
        )
        self.next_tick = None

    def run(self):
        """
        Start the SQDL Writer event loop.
        """
        try:
            logger.info("Starting SQDL Writer event loop...")
            # [x] REVIEW SdS: This is not clean.
            # [x] REVIEW SdS: Move login to init part to give feedback to user when log-in fails.
            self.next_tick = datetime.datetime.now() + self.tick_rate

            while True:
                # review todo: clean up
                # self.queue_datasets_for_export()
                self.exporter.poll()
                self.uploader.poll()
                self.sleep_to_limit_rate()

        except Exception as exc:
            logger.exception(f"An unhandled exception with the following message occured: {exc}")

        finally:
            self.uploader.disconnect_sqdl_client()
            logger.info("Stopping SQDL Writer event loop...")

    # def queue_datasets_for_export(self) -> None:
    #     """
    #      [x] REVIEW SdS: Today this comment makes sense. Next year it doesn't
    #     Covers the behaviour that would originally be done by db-sync and the remote database triggers.
    #
    #     Looks up measurement data that needs to be synchronized from the local database, and creates
    #     the appropriate ExportActions.
    #     """
    #     # [x] Review SdS: Change to simple mechanism: oldest with one flag set: export
    #     # Review SdS: Could be integrated in exporter.
    #     uids_for_data_to_update = core.get_data_to_sync(self.connection)
    #
    #     for ct_uid in uids_for_data_to_update:
    #         logger.debug(f"sync data for core-tools UID: '{ct_uid}'")
    #         export.export_changed_data(self.connection, ct_uid)
    #         core.set_data_as_synced(self.connection, ct_uid)
    #
    #     uids_for_meta_to_update = core.get_table_to_sync(self.connection)
    #
    #     # cover behaviour that would usually be handled by triggers
    #     # [x] REVIEW SdS: Simplify behavior and move to exporter.
    #     for ct_uid in uids_for_meta_to_update:
    #         sync_status = self.collect_measurement_sync_status(ct_uid)
    #         if sync_status is None:
    #             continue
    #
    #         if sync_status.is_new:
    #             export.export_new_measurement(self.connection, ct_uid, sync_status.is_complete)
    #         else:
    #             export.export_changed_measurement(self.connection, ct_uid, sync_status)
    #         core.set_table_as_synced(self.connection, ct_uid)
    #
    # def collect_measurement_sync_status(self, uuid: str) -> SyncStatus | None:
    #     """
    #     Select relevant data from 'global_measurement_overview' to use in data synchronisation.
    #     """
    #     # [x] REVIEW SdS: TODO
    #     # todo: revise how changes in name and rating are handled, because without the intermediary remote database, we lose our method for tracking changes
    #     #   in the current solution, 'local' becomes the authority on name and rating, which is not what we want
    #
    #     # [x] REVIEW SdS: See sqdl_uploader...
    #     info = core.get_measurement_info(self.connection, uuid)
    #     if info is None:
    #         logger.error(f"No local entry exists with uuid '{uuid}'.")
    #         return None
    #
    #     if info.scope is None:
    #         logger.warning(f"No Scope parameter for CoreTools UID '{info.coretools_uid}'. Skipping SQDL Sync.")
    #         return None
    #
    #     # [x] REVIEW SdS: The requests below are expensive!
    #     scope_api: sqdl_client.api.v1.scope.ScopeAPI = self.uploader.client.api.scope
    #     scope = scope_api.retrieve_from_name(info.scope)
    #
    #     try:
    #         dataset: sqdl_client.api.v1.dataset.Dataset = scope.retrieve_dataset_from_uid(str(info.coretools_uid))
    #     except sqdl_client.exceptions.ObjectNotFoundException:
    #         logger.info(f"No dataset with CoreTools UID '{info.coretools_uid}'. Creating new export.")
    #         sync_status = SyncStatus(
    #             is_new=True,
    #             is_complete=info.completed,
    #         )
    #         return sync_status
    #
    #     sync_status = SyncStatus(
    #         is_new=False,
    #         is_complete=info.completed,
    #         changed_name=info.experiment_name != dataset.name,
    #         changed_rating=info.starred != (dataset.rating > 0)
    #     )
    #     return sync_status

    def validate_version(self) -> None:
        """
        Assert that the local database version matches requirements.
        """
        get_database_version(assert_requirement=True)

    def sleep_to_limit_rate(self) -> None:
        """
        Calculate if and how long the program should sleep at the end of an event loop.
        Limits the event loop frequency to at most one iteration per ```self.tick_rate``` seconds.
        """
        now = datetime.datetime.now()
        if self.next_tick > now:
            seconds = (self.next_tick - now).total_seconds()
            time.sleep(seconds)
        self.next_tick = datetime.datetime.now() + self.tick_rate
