from core_tools.data.SQL.connect import SQL_conn_info_local, SQL_conn_info_remote, sample_info
from core_tools.data.SQL.queries.dataset_creation_queries import sample_info_queries, measurement_overview_queries
from core_tools.data.SQL.queries.dataset_sync_queries import sync_mgr_queries
import psycopg2
import time
import logging

class SQL_database_init:
    conn_local = None
    conn_remote = None
    last_commit = 0

    def _connect(self):
        self.SQL_conn_info_local = SQL_conn_info_local
        self.SQL_conn_info_remote = SQL_conn_info_remote
        self.sample_info = sample_info

        if self.conn_local is None:
            self.conn_local = psycopg2.connect(dbname=SQL_conn_info_local.dbname, user=SQL_conn_info_local.user,
                password=SQL_conn_info_local.passwd, host=SQL_conn_info_local.host, port=SQL_conn_info_local.port)
        if self.conn_remote is None:
            self.conn_remote = psycopg2.connect(dbname=SQL_conn_info_remote.dbname, user=SQL_conn_info_remote.user,
                password=SQL_conn_info_remote.passwd, host=SQL_conn_info_remote.host, port=SQL_conn_info_remote.port)

        self.last_commit = time.time()

    def _disconnect(self):
        if self.conn_local is not None:
            self.conn_local.close()
            self.conn_local = None
        if self.conn_remote is not None:
            self.conn_remote.close()
            self.conn_remote = None

    @property
    def local_conn_active(self):
        if self.SQL_conn_info_local.host == 'localhost':
            return True
        return False

    @property
    def remote_conn_active(self):
        if self.SQL_conn_info_remote.host != 'localhost':
            return True
        return False


class SQL_database_manager(SQL_database_init):
    __instance = None

    def __new__(cls):
        if SQL_database_manager.__instance is not None:
            db_mgr = SQL_database_manager.__instance
            # check connections not closed
            if (db_mgr.conn_local is None or db_mgr.conn_local.closed
                or db_mgr.conn_remote is None or db_mgr.conn_remote.closed):
                db_mgr._disconnect()
                SQL_database_manager.__instance = None
                logging.warning('Closed connections. Retry connection.')

        if SQL_database_manager.__instance is None:
            SQL_database_manager.__instance = object.__new__(cls)
            db_mgr = SQL_database_manager.__instance
            try:
                SQL_database_init._connect(db_mgr)
            except Exception:
                logging.error('Failed to connect to database', exc_info=True)
                # could not connect, for example wrong password, reset class instance
                SQL_database_manager.__instance = None
                raise

            if not db_mgr.SQL_conn_info_local.readonly:
                conn_local = db_mgr.conn_local
                sample_info_queries.generate_table(conn_local)
                sample_info_queries.add_sample(conn_local)

                measurement_overview_queries.generate_table(conn_local)
                conn_local.commit()
        return SQL_database_manager.__instance


class SQL_sync_manager(SQL_database_init):
    __instance = None
    do_sync = True

    def __new__(cls):
        if SQL_sync_manager.__instance is None:
            SQL_sync_manager.__instance = object.__new__(cls)
            SQL_database_init._connect(SQL_sync_manager.__instance)

            if not (SQL_sync_manager.__instance.remote_conn_active
                    and SQL_sync_manager.__instance.remote_conn_active):
                raise ValueError('In order to start the sync manager, a local and remote connection need to be provided.')

            sample_info_queries.generate_table(SQL_sync_manager.__instance.conn_local)
            measurement_overview_queries.generate_table(SQL_sync_manager.__instance.conn_local)

            sample_info_queries.generate_table(SQL_sync_manager.__instance.conn_remote)
            measurement_overview_queries.generate_table(SQL_sync_manager.__instance.conn_remote)
            SQL_sync_manager.__instance.conn_local.commit()
            SQL_sync_manager.__instance.conn_remote.commit()

        return SQL_sync_manager.__instance

    def rebuild_sample_info(self, remote=True):
        conn = self.conn_remote if remote else self.conn_local
        sample_info_list = sync_mgr_queries.get_sample_info_from_measurements(conn)
        sync_mgr_queries.delete_all_sample_info_overview(conn)
        print(f'Adding {len(sample_info_list)} entries to sample_info_overview')
        for entry in sample_info_list:
            project, set_up, sample = entry
            print('  adding', entry)
            sample_info_queries.add_sample(conn, project, set_up, sample)
        conn.commit()

    def run(self):
        while self.do_sync == True:
            sample_info_list = sync_mgr_queries.get_sample_info_list(self.conn_remote)
            uuid_update_list = sync_mgr_queries.get_sync_items_raw_data(self)


            for i in range(len(uuid_update_list)):
                uuid = uuid_update_list[i]
                print(f'updating raw data {i} of {len(uuid_update_list)}')
                sync_mgr_queries.sync_raw_data(self, uuid)

            if len(uuid_update_list) == 0:
                print(f'not files to update')

            uuid_update_list = sync_mgr_queries.get_sync_items_meas_table(self)

            for i in range(0,len(uuid_update_list)):
                uuid = uuid_update_list[i]
                print(f'updating table entry {i} of {len(uuid_update_list)}')
                sync_mgr_queries.sync_table(self, uuid, sample_info_list=sample_info_list)
            if len(uuid_update_list) == 0:
                print(f'not entries to update')

            time.sleep(2)

if __name__ == '__main__':
    from core_tools.data.SQL.connect import set_up_local_storage, set_up_remote_storage, set_up_local_and_remote_storage
    set_up_local_storage("xld_user", "XLDspin001", "vandersypen_data", "6dot", "XLD", "6D2S - SQ21-XX-X-XX-X")
    # set_up_local_and_remote_storage('131.180.205.81', 5432, 'stephan', 'magicc', 'test',
    #     'stephan_test', 'magicc', 'spin_data_test', 'test_project', 'test_set_up', 'test_sample')
    s = SQL_database_manager()
    print(s.conn_local)

    s2 = SQL_database_manager()

    print(s2)