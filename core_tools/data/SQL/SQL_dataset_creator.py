import time
from dataclasses import dataclass

from core_tools.data.SQL.connect import SQL_conn_info_local
from core_tools.data.SQL.SQL_connection_mgr import SQL_database_manager
from core_tools.data.SQL.queries.dataset_creation_queries import (
        sample_info_queries,
        measurement_overview_queries,
        measurement_parameters_queries
        )
from core_tools.data.SQL.queries.dataset_loading_queries import load_ds_queries
from core_tools.data.SQL.queries.dataset_sync_queries import sync_mgr_queries


class SQL_dataset_creator:

    def register_measurement(self, ds):
        '''
        Args:
            ds (data_set_raw) : raw dataset
        '''
        conn = SQL_database_manager().connection
        try:
            # add a new entry in the measurements overiew table
            sample_info_queries.add_sample(conn)

            ds.UNIX_start_time = time.time()
            ds.exp_id, ds.exp_uuid = measurement_overview_queries.new_measurement(
                    conn, ds.exp_name, ds.UNIX_start_time)
            ds.running = True

            measurement_overview_queries.update_measurement(
                    conn, ds.exp_uuid,
                    metadata=ds.metadata,
                    snapshot=ds.snapshot,
                    keywords=ds.generate_keywords(),
                    table_synchronized=False)

            # store of the getters/setters parameters
            measurement_parameters_queries.insert_measurement_params(conn, ds.exp_uuid,
                                                                     ds.measurement_parameters_raw)

            conn.commit()
        except BaseException:
            if not conn.closed:
                conn.rollback()
            raise

    def update_write_cursors(self, ds):
        '''
        update the write_cursors to the current position and commit the cached (measured) data.

        Args:
            ds (dataset_raw)
        '''
        conn = SQL_database_manager().connection
        measurement_parameters_queries.update_cursors_in_meas_tab(conn, ds.exp_uuid,
                                                                  ds.measurement_parameters_raw)
        # Update update count for synchronization process.
        # Only needed for local connection. Not available on server.
        if SQL_conn_info_local.host == 'localhost':
            ds.data_update_count += 1
            update_count = ds.data_update_count
        else:
            update_count = None
        measurement_overview_queries.update_measurement(conn, ds.exp_uuid,
                                                        data_synchronized=False,
                                                        data_update_count=update_count)
        conn.commit()

    def is_completed(self, exp_uuid):
        '''
        checks if the current measurement is still running

        Args:
            exp_uuid (int) : uuid of the experiment to check
        '''
        conn = SQL_database_manager().connection
        return measurement_overview_queries.is_completed(conn, exp_uuid)

    def finish_measurement(self, ds):
        '''

        register the mesaurement as finished in the database.

        Args:
            ds (dataset_raw)
        '''
        conn = SQL_database_manager().connection
        ds.UNIX_stop_time = time.time()

        measurement_parameters_queries.update_cursors_in_meas_tab(
            conn, ds.exp_uuid,
            ds.measurement_parameters_raw)
        measurement_overview_queries.update_measurement(
            conn, ds.exp_uuid,
            stop_time=ds.UNIX_stop_time,
            completed=True,
            data_size=ds.size(),
            table_synchronized=False,
            data_synchronized=False)

        # close the connection with the buffer to the database
        for data_item in ds.measurement_parameters_raw:
            data_item.data_buffer.close()

        conn.commit()

    def fetch_raw_dataset_by_Id(self, exp_id):
        '''
        assuming here used want to get a local id

        Args:
            exp_id (int) : id of the measurment you want to get
        '''
        conn = SQL_database_manager().connection

        if load_ds_queries.check_id(conn, exp_id) is False:
            raise ValueError(f"id {exp_id}, does not exist in this database.")

        uuid = load_ds_queries.id_to_uuid(conn, exp_id)

        return self.fetch_raw_dataset_by_UUID(uuid)

    def fetch_raw_dataset_by_UUID(self, exp_uuid, sync2local=False):
        '''
        Try to find a measurement with the corresponding uuid

        Args:
            exp_uuid (int) : uuid of the measurment you want to get
            sync2local (bool): sync measurement to local database
        '''
        db_mgr = SQL_database_manager()
        conn = db_mgr.connection
        sync = False
        if not load_ds_queries.check_uuid(conn, exp_uuid):
            if (db_mgr.remote_connection_configured
                    and load_ds_queries.check_uuid(db_mgr.remote_connection, exp_uuid)):
                conn = db_mgr.remote_connection
                sync = sync2local
            else:
                raise ValueError(f"uuid {exp_uuid}, does not exist in the local/remote database.")

        ds_raw = load_ds_queries.get_dataset_raw(db_mgr, exp_uuid)
        if sync:
            sample_info_list = sync_mgr_queries.get_sample_info_list(db_mgr.connection)
            sync_agent = _SyncAgent(db_mgr.connection, db_mgr.remote_connection)
            sync_mgr_queries.sync_raw_data(sync_agent, exp_uuid, to_local=True)
            sync_mgr_queries.sync_table(sync_agent, exp_uuid, to_local=True,
                                        sample_info_list=sample_info_list)

        return ds_raw


@dataclass
class _SyncAgent:
    conn_local: object
    conn_remote: object
