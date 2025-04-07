import os
import sys
import time
import logging
import datetime

from core_tools.data.SQL.SQL_connection_mgr import SQL_database_init as DatabaseInit, SQL_database_manager as DatabaseManager
from core_tools.data.sqdl.export.coretools_export import Exporter

from core_tools.data.SQL.versioning import get_database_version, __REQUIRED_DATABASE_VERSION__

from core_tools.data.sqdl.model import core, export
from core_tools.data.sqdl.model.export import SyncStatus

import sqdl_client
import sqdl_uploader

from psycopg2 import InterfaceError
from requests.exceptions import ConnectionError

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

        # initialise
        self.exporter = Exporter(
            cfg=config,
        )

        self.dev_mode = config.get("sqdl_sync.dev_mode", default=False)
        self.use_personal_login = config.get("sqdl_sync.use_personal_login", default=False)

        if self.dev_mode:
            logger.info("Initialising SQDL Writer/Client in developer mode...")

        self.uploader = sqdl_uploader.SqdlUploader(
            cfg=config,
        )
        self.tick_rate = datetime.timedelta(
            seconds=config.get("sqdl_sync.tick_rate", default=0.1)
        )

        # prepare for run
        self.next_tick = None

    def run(self):
        """
        Start the SQDL Writer event loop.
        """
        try:
            logger.info("Starting SQDL Writer event loop...")

            # [x] REVIEW SdS: This is not clean.

            # [ ] REVIEW SdS: Move login to init part to give feedback to user when log-in fails.
            if self.use_personal_login and not self.dev_mode:
                # [ ] REVIEW SdS: delegate functionality to uploader. "Don't grab my wallet. Ask me to pay."
                self.uploader.client.login()

                # TODO SdS: do this in a clean way in uploader
                # Solution A: retrieve from OIDC
                user_info = self.uploader.client.user_info
                if user_info is None:
                    logger.error("ATTENTION: You are logged in as an unidentified user !!")
                    # TODO SdS: Exit?
                else:
                    print(f"You are logged in on sQDL as user '{user_info['name']}'")

                # Solution B: retrieve user from sqdl
                user_api = self.upload.client.api.user
                user = user_api.whoami()
                print(f"You are logged in on sQDL as user '{user.name}'")


            elif (not self.use_personal_login and not self.dev_mode) or (self.use_personal_login is None):
                # [ ] REVIEW SdS: 4 options
                # - normal + api key: Default UPL and dev both False
                # - normal + personal login: UPL = True, dev = False @@@ Do we wwant this in lab?
                # - dev mode + basic auth: dev = "basic"
                # - dev mode + api key: dev = "api_key"

                # added personal-login as none option as a hack to force API key usage in developer mode
                key = self.read_local_api_key()
                if key is None:
                    # [ ] REVIEW SdS: Why exit the hard way and not raise Exception?
                    raise Exception("KeyNotFoundException")
                self.uploader.client.use_api_key(key)

            self.next_tick = datetime.datetime.now() + self.tick_rate

            while True:
                try:
                    self.queue_datasets_for_export()
                    self.exporter.poll()
                    self.uploader.poll()

                except InterfaceError as error:
                    # [ ] Review SdS: Shouldn't happen on local PC. Correct to raise and thus quit program.
                    logger.error("Connection to local database lost.")
                    raise error

                except ConnectionError:
                    # ConnectionError is also caught by uploader. It should never get here.
                    logger.warning("Failed to connect to SQDL. ")

                finally:
                    self.sleep_to_limit_rate()

        except Exception as exc:
            logger.exception(f"An unhandled exception with the following message occured: {exc}")

        finally:
            self.database._disconnect()
            self.uploader.client.logout()
            logger.info("Stopping SQDL Writer event loop...")

    def queue_datasets_for_export(self) -> None:
        """
         [ ] REVIEW SdS: Today this comment makes sense. Next year it doesn't
        Covers the behaviour that would originally be done by db-sync and the remote database triggers.

        Looks up measurement data that needs to be synchronized from the local database, and creates
        the appropriate ExportActions.
        """
        # [ ] Review SdS: Change to simple mechanism: oldest with one flag set: export
        # Review SdS: Could be integrated in exporter.
        uids_for_data_to_update = core.get_data_to_sync(self.connection)

        for ct_uid in uids_for_data_to_update:
            logger.debug(f"sync data for core-tools UID: '{ct_uid}'")
            export.export_changed_data(self.connection, ct_uid)
            core.set_data_as_synced(self.connection, ct_uid)

        uids_for_meta_to_update = core.get_table_to_sync(self.connection)

        # cover behaviour that would usually be handled by triggers
        # [ ] REVIEW SdS: Simplify behavior and move to exporter.
        for ct_uid in uids_for_meta_to_update:
            sync_status = self.collect_measurement_sync_status(ct_uid)
            if sync_status is None:
                continue

            if sync_status.is_new:
                export.export_new_measurement(self.connection, ct_uid, sync_status.is_complete)
            else:
                export.export_changed_measurement(self.connection, ct_uid, sync_status)
            core.set_table_as_synced(self.connection, ct_uid)

    def collect_measurement_sync_status(self, uuid: str) -> SyncStatus | None:
        """
        Select relevant data from 'global_measurement_overview' to use in data synchronisation.
        """
        # [ ] REVIEW SdS: TODO
        # todo: revise how changes in name and rating are handled, because without the intermediary remote database, we lose our method for tracking changes
        #   in the current solution, 'local' becomes the authority on name and rating, which is not what we want

        # [ ] REVIEW SdS: See sqdl_uploader...
        info = core.get_measurement_info(self.connection, uuid)
        if info is None:
            logger.error(f"No local entry exists with uuid '{uuid}'.")
            return None

        if info.scope is None:
            logger.warning(f"No Scope parameter for CoreTools UID '{info.coretools_uid}'. Skipping SQDL Sync.")
            return None

        # [ ] REVIEW SdS: The requests below are expensive!
        scope_api: sqdl_client.api.v1.scope.ScopeAPI = self.uploader.client.api.scope
        scope = scope_api.retrieve_from_name(info.scope)

        try:
            dataset: sqdl_client.api.v1.dataset.Dataset = scope.retrieve_dataset_from_uid(str(info.coretools_uid))
        except sqdl_client.exceptions.ObjectNotFoundException:
            logger.info(f"No dataset with CoreTools UID '{info.coretools_uid}'. Creating new export.")
            sync_status = SyncStatus(
                is_new=True,
                is_complete=info.completed,
            )
            return sync_status

        sync_status = SyncStatus(
            is_new=False,
            is_complete=info.completed,
            changed_name=info.experiment_name != dataset.name,
            changed_rating=info.starred != (dataset.rating > 0)
        )
        return sync_status

    def validate_version(self) -> None:
        """
        Assert that the local database version matches requirements.
        """
        version = get_database_version(self.connection)
        assert version == __REQUIRED_DATABASE_VERSION__, (
            f"Local database is not up to date (expected '{__REQUIRED_DATABASE_VERSION__}', found '{version}'). "
            "Cannot sync to SQDL."
        )

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

    def read_local_api_key(self) -> str | None:
        env_file = f"{self.base_path}/.env"

        if not os.path.exists(env_file):
            logger.error("No .env file found. Check the 'Using SQDL' section of the documentation, "
                         "or ask your local Admin for the right credentials.")
            return None

        with open(env_file) as file:
            lines = file.readlines()

        for line in lines:
            if line.startswith("#"):
                continue
            key, value = line.strip().split(sep="=", maxsplit=1)
            if key == "API_KEY":
                return value

        logger.error("Found .env file, but unable to extract parameter 'API_KEY'. "
                     "Check the 'Using SQDL' section of the documentation for more details.")
        return None
