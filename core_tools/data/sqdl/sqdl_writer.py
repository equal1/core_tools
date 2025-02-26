import time
import logging
from typing import Optional
import datetime

from core_tools.startup.config import get_configuration
from core_tools.data.SQL.SQL_connection_mgr import SQL_database_init as DatabaseInit
from core_tools.data.sqdl.export.coretools_export import Exporter
from core_tools.data.sqdl.uploader.sqdl_uploader import SqdlUploader as Uploader

from core_tools.data.sqdl.model import core, export, version
from core_tools.data.sqdl.model.export import SyncStatus

import sqdl_client
from sqdl_client.client import QDLClient

from psycopg2 import InterfaceError
from requests.exceptions import ConnectionError

__database_version__ = "1.1.0"

logger = logging.getLogger(__name__)


class SQDLWriter():
    """
    Event loop that polls for measurement data to be uploaded to SQDL.
    Expects the core-tools configurations to be initialised (see core-tools/startup/config.py).
    Start the loop using the 'run' method.
    """

    def __init__(self):
        config = get_configuration()

        # local database
        self.database = DatabaseInit()
        self.database._connect()
        if not self.database.local_conn_active:
            raise ValueError("database not configured to a local database instance")
        self.connection = self.database.conn_local
        self.validate_version()

        # initialise
        self.exporter = Exporter(
            cfg=config,
            conn=self.connection
        )
        self.dev_mode = config.get("sqdl.dev_mode", default=True)
        if self.dev_mode:
            logger.info("Initialising SQDL Writer/Client in developer mode...")
        self.uploader = Uploader(
            cfg=config,
            conn=self.connection,
            client=QDLClient(
                dev_mode=self.dev_mode,
            )
        )
        self.tick_rate = datetime.timedelta(
            seconds=config.get("sqdl.tick_rate", default=6)
        )

        # prepare for run
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
            self.exporter.connection = self.connection
            self.uploader.connection = self.connection

            self.is_running = True
            self.next_tick = datetime.datetime.now() + self.tick_rate

            while self.is_running:
                try:
                    self.queue_datasets_for_export()
                    self.exporter.poll()
                    self.uploader.poll()

                except InterfaceError as error:
                    logger.warning("Connection to local database lost.")
                    raise error
                    # logger.warning("Connection to local database lost. Reconnecting...")
                    # self.reconnect()

                except ConnectionError:
                    logger.warning("Failed to connect to SQDL. ")

                finally:
                    self.sleep_to_limit_rate()

        except Exception as exc:
            logger.exception("An unhandled exception with the following message occured: {}".format(exc))

        finally:
            self.database._disconnect()
            logger.info("Stopping SQDL Writer event loop...")

    def queue_datasets_for_export(self) -> None:
        """
        Covers the behaviour that would originally be done by db-sync and the remote database triggers.
        Looks up measurement data that needs to be synchronized from the local database, and creates the appropriate ExportActions.
        """
        uids_for_data_to_update = core.get_data_to_sync(self.connection)

        for ct_uid in uids_for_data_to_update:
            logger.debug("sync data for core-tools UID: '{}'".format(ct_uid))

            # todo: these two belong together, right?
            export.export_changed_data(self.connection, ct_uid)
            core.set_data_as_synced(self.connection, ct_uid)

        uids_for_meta_to_update = core.get_table_to_sync(self.connection)

        # cover behaviour that would usually be handled by triggers
        for ct_uid in uids_for_meta_to_update:
            sync_status = self.collect_measurement_sync_status(ct_uid)
            if sync_status is None:
                continue

            if sync_status.is_new:
                export.export_new_measurement(self.connection, ct_uid, sync_status.is_complete)
            else:
                export.export_changed_measurement(self.connection, ct_uid, sync_status)
            core.set_table_as_synced(self.connection, ct_uid)

    def collect_measurement_sync_status(self, uuid: str) -> Optional[SyncStatus]:
        """
        Select relevant data from 'global_measurement_overview' to use in data syncronisation.
        """
        # todo: check local data agains SQDL remote data
        # todo: revise how changes in name and rating are handled, because without the intermediary remote database, we lose our method for tracking changes
        #   in the current solution, 'local' becomes the authority on name and rating, which is not what we want
        statement = """
            SELECT overview.uuid, overview.scope, overview.exp_name, overview.starred, overview.completed, datasets.sqdl_uuid
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

        ct_uid, scope_name, ct_name, ct_star, ct_complete, sqdl_uuid = result

        if scope_name is None:
            logger.warning("No Scope parameter for CoreTools UID '{}'. Skipping SQDL Sync.".format(ct_uid))
            return None

        # do not use 'login' functionality when doing local development
        if not self.dev_mode:
            self.uploader.client.login()

        scope_api: sqdl_client.api.v1.scope.ScopeAPI = self.uploader.client.api.scope
        scope = scope_api.retrieve_from_name(scope_name)

        try:
            dataset: sqdl_client.api.v1.dataset.Dataset = scope.retrieve_dataset_from_uid(str(ct_uid))
        except sqdl_client.exceptions.ObjectNotFoundException:
            logger.info("No dataset with CoreTools UID '{}'. Creating new export.".format(ct_uid))
            metadata = SyncStatus(
                is_new=True,
                is_complete=ct_complete,
            )
            return metadata

        metadata = SyncStatus(
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
        database_version = version.read(self.connection)

        assert database_version == __database_version__, "Database is not up to date: expected '{}', found '{}'".format(__database_version__, database_version)

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

    def reconnect(self):
        self.database._disconnect()
        self.database._connect()
        self.connection = self.database.conn_local
        assert self.connection.closed == 0, "failed to reconnect"

        self.exporter.connection = self.connection
        self.uploader.connection = self.connection
