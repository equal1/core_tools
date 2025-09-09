import time
import logging

from .db_connections import connect_local_db, connect_remote_db
from .queries.dataset_sync_queries import sync_mgr_queries
from .queries.dataset_creation_queries import (
    sample_info_queries,
    measurement_overview_queries,
    measurement_parameters_queries)


logger = logging.getLogger(__name__)


class SQL_sync_manager():
    do_sync = True

    def __init__(self):
        self.conn_local = None
        self.conn_remote = None
        self.init_connections()

        sample_info_queries.generate_table(self.conn_local)
        measurement_overview_queries.generate_table(self.conn_local)
        measurement_parameters_queries.generate_table(self.conn_local)

        sample_info_queries.generate_table(self.conn_remote)
        measurement_overview_queries.generate_table(self.conn_remote)
        measurement_parameters_queries.generate_table(self.conn_remote)
        self.conn_local.commit()
        self.conn_remote.commit()

    def init_connections(self):
        if self.conn_local is None or self.conn_local.closed:
            self.conn_local = connect_local_db()

        if self.conn_remote is None or self.conn_remote.closed:
            self.conn_remote = connect_remote_db()

    def rebuild_sample_info(self, remote=True):
        conn = self.conn_remote if remote else self.conn_local
        sample_info_list = sync_mgr_queries.get_sample_info_from_measurements(conn)
        # sync_mgr_queries.delete_all_sample_info_overview(conn)
        self.log(f'Adding {len(sample_info_list)} entries to sample_info_overview')
        for entry in sample_info_list:
            project, set_up, sample = entry
            self.log(f"  adding {entry}")
            sample_info_queries.add_sample(conn, project, set_up, sample)
        conn.commit()

    def run(self):
        while SQL_sync_manager.do_sync:
            self.init_connections()
            sample_info_list = sync_mgr_queries.get_sample_info_list(self.conn_remote)
            uuid_update_list = sync_mgr_queries.get_sync_items_raw_data(self)

            for i in range(len(uuid_update_list)):
                uuid = uuid_update_list[i]
                self.log(f'updating raw data {i} of {len(uuid_update_list)}')
                sync_mgr_queries.sync_raw_data(self, uuid)

            if len(uuid_update_list) == 0:
                self.log('no raw data to update')

            uuid_update_list = sync_mgr_queries.get_sync_items_meas_table(self)

            for i in range(0, len(uuid_update_list)):
                uuid = uuid_update_list[i]
                self.log(f'updating table entry {i} of {len(uuid_update_list)}')
                sync_mgr_queries.sync_table(self, uuid, sample_info_list=sample_info_list)
            if len(uuid_update_list) == 0:
                self.log('no entries to update')

            time.sleep(2)

    def log(self, message):
        print(message)
        logger.info(message)
