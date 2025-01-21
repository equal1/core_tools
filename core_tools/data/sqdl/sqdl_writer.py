import time
import logging
from typing import Tuple, Optional
import datetime

from core_tools.startup.config import get_configuration
from core_tools.data.SQL.SQL_connection_mgr import SQL_database_init as DatabaseInit
from core_tools.data.SQL.queries.dataset_sync_queries import sync_mgr_queries
from core_tools.data.export.coretools_export import Exporter
from core_tools.data.sqdl.sqdl_uploader import SqdlUploader as Uploader

import sqdl_client
from sqdl_client.client import QDLClient
from sqdl_client.utils.fakes.fake_client import QDLFake


logger = logging.getLogger(__name__)


def _create_fake_client() -> QDLClient:
    schema_name = "coretools-default"
    qdl_fake = QDLFake()
    qdl_fake.add_schema(
        schema_name,
        '''
        measurement_data(
            setup(min_length=5, type=str),
            sample(min_length=5),
            variables_measured(type=list),
            dimensions(type=list))
        ''')

    for scope_name in ["Test",]:
        qdl_fake.add_scope(scope_name, 'Scope to test QDL', schema_name)

    return qdl_fake.client


class SQDLWriter():
    """
    Event loop that polls for measurement data to be uploaded to SQDL.
    Expects the core-tools configurations to be initialised (see core-tools/startup/config.py).
    Start the loop using the 'run' method.
    """

    def __init__(self):
        self.config = get_configuration()

        self.database = DatabaseInit()
        self.database._connect()
        self.create_export_tables_if_not_exist()  # done: create required tables if they do not exist yet

        # done: make sure that exporter creates the required tables --> already did using SQLalchemy ORM
        self.exporter = Exporter(self.config)

        client = None
        if self.config.get("use-sqdl-testing-environment", default=True):  # to-do: change default to False when wrapping up
            logger.info("Using fake SQDL Client for testing purposes")
            client = _create_fake_client()
        self.uploader = Uploader(self.config, client=client)

        self.tick_rate = datetime.timedelta(
            seconds=self.config.get("tick_rate", default=10)
        )
        self.is_running = False

    def run(self):
        """
        Start the SQDL Writer event loop.
        """
        self.database._connect()  # okay to skip disconnect, since the loop only stops at Writer shutdown (otherwise, use try-finally block or create context manager)
        self.is_running = True

        next_tick = datetime.datetime.now() + self.tick_rate
        while self.is_running:
            # done: identify data that needs to be handled
            uuids_for_data_to_update = sync_mgr_queries.get_sync_items_raw_data(self.database)  # checks 'data-synchronised' column value

            # validate that the work done by db-sync does not significantly alter the contents of the postgresql database
            # done: check contents of "sync raw data" method
            # - query on UUID for 'data location', 'sync location' and 'update count'
            # - data location and sync location just used for old output format
            # - update count used to set 'data-synchronised' to true, so the entry is only processed once
            # - the sync process deletes all remote data, then re-writes local data to remote
            # -- this means that the entire section is trivialised by having only local data
            # -- need to set the 'data synchronised' column
            for uuid in uuids_for_data_to_update:
                logger.debug("sync data for uuid: '{}'".format(uuid))
                # (correction) done: part of the work is being done by the database triggers on the remote database -> insert into Exporter's database that data has changed (see ExportAction)
                self.export_changed_measurement_data(uuid)
                self.register_data_as_synchronised(uuid)

            uuids_for_meta_to_update = sync_mgr_queries.get_sync_items_meas_table(self.database)  # checks 'table synchronised' column value
            # done: check contents of "sync table" method

            # [!] previously, the 'new-measurement' status could be derived from a 'uuid' existing in local and not existing in remote. Need to find a new mechanism to trigger 'export-new-measurement' (to be validated)
            # >> same problem applied to 'star changed' and 'name changed'
            # >> should be that 'data update count' column starts at 0 for new measurements, marking a clear beginning. Have to test for edge cases

            #   - uuids for data to update will result in triggers for 'measurement-parameter' table
            #   - uuids for meta to update will result in triggers for 'global-overview' table

            # cover behaviour that would usually be handled by triggers
            for uuid in uuids_for_meta_to_update:
                # to-do: parse data from 'global_measurement_overview'
                # to-do: check local data agains SQDL remote data
                metadata = self.collect_measurement_info(uuid)
                if metadata is None:
                    continue

                if self.check_if_uuid_is_new(metadata):
                    self.export_new_measurement(
                        uuid=uuid,
                        completed=metadata.get("is_complete", default=False)
                    )
                else:
                    # done: assert if there are any edge cases that reach this point without ever running export_new_measurement()
                    star_changed, name_changed = self.check_for_measurement_changes(metadata)
                    self.export_changed_measurement(
                        uuid=uuid,
                        complete=metadata.get("is_complete", default=False),
                        star_changed=star_changed,
                        name_changed=name_changed,
                    )

                # done: label table as synchronised
                self.register_table_as_synchronised(uuid)

            # export datasets
            # to-do: check if there is a good way to export more than one action
            #   ExportAction stack can grow quite a bit, since one event loop check for all local changes,
            #   but only exports one (maybe temporary growing of the task stack is not harmful)
            self.exporter.poll()
            # done: modify exporter to use a poll method instead of a run method
            # done: modify exporter to use PostgreSQL instead of SQLite

            # update datasets
            self.uploader.poll()
            pass  # done: modify uplaoder to use a poll method instead of a run method
            pass  # done: modify uploader to use PostgreSQL instead of SQLite --> (same class as exporter)

            # done: sleep for deltatime if loop is running too fast
            now = datetime.datetime.now()
            if next_tick > now:
                time.sleep((next_tick - now).total_seconds())
            logger.debug("tick")
            next_tick = datetime.datetime.now() + self.tick_rate

    def create_export_tables_if_not_exist(self):
        with self.database.conn_local.cursor() as cur:
            table_statement, index_statement = self._create_export_updates_table()
            cur.execute(table_statement)
            cur.execute(index_statement)

            table_statement, index_statement = self._create_exported_table()
            cur.execute(table_statement)
            cur.execute(index_statement)

    def _create_export_updates_table(self) -> Tuple[str, str]:
        """
        Provides the statements to create the coretools-export-updates table, if it does not already exist.

        The following five columns function as boolean flag that dictate operations.
        new-measurement - not really needed, but overwrites all data
        data-changed - export previews, export metadata
        completed - export raw data
        update-star - compare with exported metadata
        update-name - compare with exported metadata
        """
        create_table_statement = """
        CREATE TABLE IF NOT EXISTS coretools_export_updates (
           id INT GENERATED ALWAYS AS IDENTITY,
           uuid BIGINT NOT NULL UNIQUE,
           modify_count INT default 0,

           new_measurement BOOLEAN default FALSE,
           data_changed BOOLEAN default FALSE,
           completed BOOLEAN default FALSE,
           update_star BOOLEAN default FALSE,
           update_name BOOLEAN default FALSE,

           PRIMARY KEY(id)
        );
        """
        create_index_statement = """
        CREATE INDEX IF NOT EXISTS qdl_export_updates_uuid_index ON coretools_export_updates USING BTREE (uuid);
        """
        return create_table_statement, create_index_statement

    def _create_exported_table(self) -> Tuple[str, str]:
        """
        Provides the statements to create the coretools-exported table, if it does not already exist.
        """
        create_table_statement = """
        CREATE TABLE IF NOT EXISTS coretools_exported (
           id INT GENERATED ALWAYS AS IDENTITY,
           uuid BIGINT NOT NULL UNIQUE,
           path TEXT,
           measurement_start_time timestamp, -- export raw after timeout and not completed.
           raw_final BOOLEAN default FALSE, -- Set when completed or after timeout.

           -- export state
           export_state INT default 0, -- (0:todo, 1:done, 99: failed),
           export_errors TEXT,

           PRIMARY KEY(id)
        );
        """
        create_index_statement = """
        CREATE INDEX IF NOT EXISTS coretools_exported_uuid_index ON coretools_exported USING BTREE (uuid);
        """
        return create_table_statement, create_index_statement

    def export_new_measurement(self, uuid: int, completed: bool):
        """
        Original behaviour triggered on INSERT operations in the 'global_measurement_overview' table.
        """
        statement = """
        INSERT INTO coretools_export_updates(uuid, new_measurement, data_changed, completed)
        VALUES (%{uuid}s, TRUE, TRUE, %(completed)s)
        ON CONFLICT (uuid) DO
          UPDATE SET
             modify_count = coretools_export_updates.modify_count + 1,
             new_measurement = TRUE,
             completed = %(completed)s;
        """
        parameters = {
            "uuid": uuid,
            "completed": completed,
        }
        with self.database.conn_local.cursor() as cur:
            cur.execute(
                query=statement,
                vars=parameters,
            )

    def export_changed_measurement(self, uuid, complete: bool, star_changed: bool, name_changed: bool):
        """
        Original behaviour triggered on UPDATE operations in the 'global_measurement_overview' table.
        """
        statement = """
        INSERT INTO coretools_export_updates(uuid, update_star, update_name, completed)
        VALUES (%(uuid)s, %(update-star)s, %(name-changed)s, %(completed)s)
        ON CONFLICT (uuid) DO
          UPDATE SET
             modify_count = coretools_export_updates.modify_count + 1,
             update_star = coretools_export_updates.update_star OR %(star-changed)s,
             update_name = coretools_export_updates.update_name OR %(name-changed)s,
             completed = NEW.completed;
        """
        parameters = {
            "uuid": uuid,
            "star-changed": star_changed,  # star value in global-overview not equal to new value
            "name-changed": name_changed,  # experiment name value in global-overview not equal to new value
            "completed": complete
        }
        with self.database.conn_local.cursor() as cur:
            cur.execute(
                query=statement,
                vars=parameters,
            )

    def export_changed_measurement_data(self, uuid):
        """
        Original behaviour triggered on INSERT and UPDATE operations in the 'measurement_parameters' table.
        """
        statement = """
        INSERT INTO coretools_export_updates(uuid, data_changed)
        VALUES (%(uuid)s, TRUE)
        ON CONFLICT (uuid) DO
          UPDATE SET
             modify_count = coretools_export_updates.modify_count + 1,
             data_changed = TRUE;
        """
        parameters = {
            "uuid": uuid
        }
        with self.database.conn_local.cursor() as cur:
            cur.execute(
                query=statement,
                vars=parameters,
            )

    def register_data_as_synchronised(self, uuid) -> None:
        """
        Update 'global_measurement_overview' to register measurement data as synchronised
        """
        statement = """
        UPDATE global_measurement_overview
        SET data_synchronized = TRUE
        WHERE uuid = %(uuid)s;
        """
        parameters = {
            "uuid": uuid
        }
        with self.database.conn_local.cursor() as cur:
            cur.execute(
                query=statement,
                vars=parameters,
            )

    def register_table_as_synchronised(self, uuid) -> None:
        """
        Update 'global_measurement_overview' to register measurement table as synchronised
        """
        statement = """
        UPDATE global_measurement_overview
        SET table_synchronized = TRUE
        WHERE uuid = %(uuid)s;
        """
        parameters = {
            "uuid": uuid
        }
        with self.database.conn_local.cursor() as cur:
            cur.execute(
                query=statement,
                vars=parameters,
            )

    def collect_measurement_info(self, uuid) -> Optional[dict]:
        """
        Select relevant data from 'global_measurement_overview' to use in data syncronisation.
        """
        # to-do: replace dict with static type (?)
        statement = """
        SELECT exp_name, starred, completed FROM global_measurement_overview WHERE uuid = %(uuid)s;
        """
        parameters = {
            "uuid": uuid
        }
        result = None
        with self.database.conn_local.cursor() as cur:
            cur.execute(
                query=statement,
                vars=parameters,
            )
            result = cur.fetchone()
        if result is None:
            logger.error("Failed to fetch data, or no entry exists with uuid '{}'".format(uuid))
            return None

        # to-do: fetch SQDL status on 'starred' and 'experiment-name' parameters, for comparison
        self.uploader.client.login()

        # schema: sqdl_client.api.v1.schema.SchemaAPI = self.uploader.client.api.schemas
        # logger.info(schema.list())
        # schema_instance = schema.retrieve_from_name("coretools-default")
        # logger.info(schema_instance.to_json())

        scope_api: sqdl_client.api.v1.scope.ScopeAPI = self.uploader.client.api.scope
        # logger.info(scope_api.list())

        scope = scope_api.retrieve_from_name("Test")
        # logger.info(scope.list_data_identifiers())
        logger.info("dataset uid: {}".format(uuid))
        try:
            dataset: sqdl_client.api.v1.dataset.Dataset = scope.retrieve_dataset_from_uid(uuid)
        except sqdl_client.exceptions.ObjectNotFoundException as err:
            logger.error(err)
            return None

        logger.info("dataset name: {}".format(dataset.name))
        logger.info("dataset rating: {}".format(dataset.rating))

        metadata = {
            "is_new": False,
            "is_complete": False,
            "name_changed": False,
            "star_changed": False,
        }
        return metadata

    def check_if_uuid_is_new(self, uuid) -> bool:
        """
        'update count' is 0
        """
        statement = """
        SELECT data_update_count
        FROM global_measurement_overview
        WHERE uuid = %(uuid)s;
        """
        # to-do: fix check for new data
        logger.warning("column value 'data_update_count' equal to 0 is not a safe test for new data: measurement can easily do multiple updates within one polling round, creating a race-condition")

        parameters = {
            "uuid": uuid
        }
        with self.database.conn_local.cursor() as cur:
            cur.execute(
                query=statement,
                vars=parameters,
            )
            result = cur.fetchone()
            assert result is not None, "Already queries UUID cannot be None"

        return result[0] == 0
