import time
import logging
from typing import Optional
import datetime

from core_tools.startup.config import get_configuration
from core_tools.data.SQL.SQL_connection_mgr import SQL_database_init as DatabaseInit
from core_tools.data.sqdl.export.coretools_export import Exporter
from core_tools.data.sqdl.uploader.sqdl_uploader import SqdlUploader as Uploader

from core_tools.data.sqdl.model import core, export, version
from core_tools.data.sqdl.model.export import Metadata

import sqdl_client
from sqdl_client.client import QDLClient

__database_version__ = "1.1.0"

logger = logging.getLogger(__name__)


class SQDLWriter():
    """
    Event loop that polls for measurement data to be uploaded to SQDL.
    Expects the core-tools configurations to be initialised (see core-tools/startup/config.py).
    Start the loop using the 'run' method.
    """

    def __init__(self):
        # configuration
        config = get_configuration()

        # local database
        self.database = DatabaseInit()

        self.database._connect()
        self.connection = self.database.conn_local
        self.validate_version()

        # core
        self.exporter = Exporter(config)
        self.uploader = Uploader(
            config,
            conn=self.connection,
            client=QDLClient(
                dev_mode=config.get("sqdl.dev_mode", default=True)
            )
        )

        # event loop
        self.tick_rate = datetime.timedelta(
            seconds=config.get("sqdl.tick_rate", default=6)
        )
        self.is_running = False
        self.next_tick = None
        self.database._disconnect()

    def run(self):
        """
        Start the SQDL Writer event loop.
        """
        try:
            logger.info("Starting SQDL Writer event loop...")

            self.database._connect()
            self.connection = self.database.conn_local

            self.is_running = True
            self.next_tick = datetime.datetime.now() + self.tick_rate

            while self.is_running:
                if self.connection.closed > 0:
                    logger.warning("Connection to local database lost. Reconnecting...")
                    self.database._disconnect()
                    self.database._connect()
                    self.connection = self.database.conn_local
                    assert self.connection.closed == 0, "failed to reconnect"
                    # todo: instead of passing connection every time, set connection for exporter and uploader here once. If any of the components closes the connection, the reconnect will be triggered.

                self.queue_datasets_for_export()
                # todo: check if there is a good way to export more than one action
                #   ExportAction stack can grow quite a bit, since one event loop check for all local changes,
                #   but only exports one (maybe temporary growing of the task stack is not harmful)
                self.exporter.poll(self.connection)
                self.uploader.poll(self.connection)

                self.sleep_to_limit_rate()

        except Exception as exc:
            logger.exception("An Exception with the following message occured: {}".format(exc))

        finally:
            self.database._disconnect()
            logger.info("Stopping SQDL Writer event loop...")

    def queue_datasets_for_export(self):
        """
        Covers the behaviour that would originally be done by db-sync and the remote database triggers.
        Looks up measurement data that needs to be synchronized from the local database, and creates the appropriate ExportActions.
        """
        with self.connection:
            cursor = self.connection.cursor()
            uids_for_data_to_update = core.CoreOperations().get_data_to_sync(cursor)

            for ct_uid in uids_for_data_to_update:
                logger.debug("sync data for core-tools UID: '{}'".format(ct_uid))
                export.ExportOperations().export_changed_data(cursor, ct_uid)
                core.CoreOperations().set_data_as_synced(cursor, ct_uid)

        with self.connection:
            cursor = self.connection.cursor()
            uids_for_meta_to_update = core.CoreOperations().get_table_to_sync(cursor)

        # cover behaviour that would usually be handled by triggers
        for ct_uid in uids_for_meta_to_update:
            metadata = self.collect_measurement_status(ct_uid)
            if metadata is None:
                continue

            with self.connection:
                cursor = self.connection.cursor()
                if metadata.is_new:
                    export.ExportOperations().export_new_measurement(cursor, ct_uid, metadata.is_complete)
                else:
                    export.ExportOperations().export_changed_measurement(cursor, ct_uid, metadata)
                core.CoreOperations().set_table_as_synced(cursor, ct_uid)

    def collect_measurement_status(self, uuid: str) -> Optional[Metadata]:
        """
        Select relevant data from 'global_measurement_overview' to use in data syncronisation.
        """
        # todo: check local data agains SQDL remote data
        # todo: revise how changes in name and rating are handled, because without the intermediary remote database, we lose our method for tracking changes
        #   in the current solution, 'local' becomes the authority on name and rating, which is not what we want
        statement = """
            SELECT overview.uuid, overview.exp_name, overview.starred, overview.completed, datasets.sqdl_uuid
            FROM global_measurement_overview AS overview
            JOIN sqdl_dataset AS datasets
            ON overview.uuid = datasets.coretools_uid
            WHERE overview.uuid = %(ct-uid)s;
        """
        parameters = {
            "ct-uid": uuid
        }

        result = None
        with self.connection:
            cur = self.connection.cursor()
            cur.execute(
                query=statement,
                vars=parameters,
            )
            result = cur.fetchone()
        if result is None:
            logger.error("Failed to fetch data, or no entry exists with uuid '{}'".format(uuid))
            return None

        ct_uid, ct_name, ct_star, ct_complete, sqdl_uuid = result

        # statement = """
        # SELECT exp_name, starred, completed FROM global_measurement_overview WHERE uuid = %(uuid)s;
        # """
        # statement = """
        # SELECT sqdl_uuid FROM uploaded_dataset WHERE uid = %(uid)s;
        # """

        # # do not use 'login' functionality when doing local development
        # self.uploader.client.login()

        scope_api: sqdl_client.api.v1.scope.ScopeAPI = self.uploader.client.api.scope
        scope = scope_api.retrieve_from_name("scope_command_generated_1")

        logger.info("dataset uid: {}".format(ct_uid))
        try:
            dataset: sqdl_client.api.v1.dataset.Dataset = scope.retrieve_dataset_from_uid(str(ct_uid))
            logger.info("found dataset")
        except sqdl_client.exceptions.ObjectNotFoundException as err:
            logger.info("No dataset with CoreTools UID '{}'. SQDL response: {}".format(ct_uid, err))
            metadata = Metadata(
                is_new=True,
                is_complete=ct_complete,
            )
            return metadata

        logger.info("dataset name: {}".format(dataset.name))
        logger.info("dataset rating: {}".format(dataset.rating))
        metadata = Metadata(
            is_new=False,
            is_complete=ct_complete,
            changed_name=ct_name != dataset.name,
            changed_rating=ct_star != (dataset.rating > 0)
        )
        return metadata

    def validate_version(self) -> None:
        """
        Assert that the local database version matches requirements.
        """
        with self.connection as conn:
            cursor = conn.cursor()
            database_version = version.VersionOperations().read(cursor)

        assert database_version == __database_version__, "Database is not up to date: expected '{}', found '{}'".format(__database_version__, database_version)

    def sleep_to_limit_rate(self) -> None:
        now = datetime.datetime.now()
        if self.next_tick > now:
            seconds = (self.next_tick - now).total_seconds()
            logger.info("Sleep for {} seconds as rate-limit".format(seconds))
            time.sleep(seconds)
        else:
            logger.info("Too busy to sleep!")
        self.next_tick = datetime.datetime.now() + self.tick_rate
