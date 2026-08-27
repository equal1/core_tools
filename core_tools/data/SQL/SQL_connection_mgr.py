import logging

from .connect import SQL_conn_info_local, SQL_conn_info_remote
from .db_connections import connect_local_db, connect_remote_db
from .model.version import local_database_update_routine
from .queries.dataset_creation_queries import (
    measurement_overview_queries,
    measurement_parameters_queries,
    sample_info_queries,
)

# import for backwards campatibility of old scripts.


logger = logging.getLogger(__name__)


class SQL_database_manager:
    _connection = None
    _remote_connection = None
    _connection_configured = False

    @property
    def connection(self):
        cls = SQL_database_manager
        if cls._connection is None or getattr(cls._connection, "closed", False):
            cls._connect()
        return cls._connection

    # backward compatible property names
    @property
    def conn_local(self):
        """Alias for :attr:`connection` for backward compatibility."""
        return self.connection

    @property
    def conn_remote(self):
        """Alias for :attr:`remote_connection` for backward compatibility."""
        return self.remote_connection

    @property
    def remote_connection(self):
        cls = SQL_database_manager
        if cls._remote_connection is None or getattr(
            cls._remote_connection, "closed", False
        ):
            cls._connect_remote()
        return cls._remote_connection

    @property
    def remote_connection_configured(self):
        return SQL_conn_info_remote.host is not None

    @classmethod
    def disconnect(cls):
        if cls._connection is not None:
            cls._connection.close()
            cls._connection = None

        if cls._remote_connection is not None:
            cls._remote_connection.close()
            cls._remote_connection = None

    @staticmethod
    def init_server():
        if SQL_conn_info_remote.host is None:
            raise Exception("Remote server not configured")
        conn = SQL_database_manager().remote_connection

        sample_info_queries.generate_table(conn)

        measurement_overview_queries.generate_table(conn)
        measurement_parameters_queries.generate_table(conn)
        conn.commit()

    @classmethod
    def _connect(cls):
        if cls._connection is not None and not getattr(
            cls._connection, "closed", False
        ):
            cls._connection.close()

        if SQL_conn_info_local.dbname is not None:
            cls._connection = connect_local_db()
            if not cls._connection_configured:
                cls._configure_local_db()
        elif SQL_conn_info_remote.dbname is not None:
            cls._connection = connect_remote_db()
        else:
            raise Exception("No database configured")

    @classmethod
    def _configure_local_db(cls):
        conn = cls._connection
        if SQL_conn_info_local.is_sqlite:
            # The measurement-dataset schema and its migrations are PostgreSQL
            # only: SERIAL columns, USING BTREE indexes, ADD COLUMN IF NOT
            # EXISTS, multi-statement execute() and psycopg2 error codes. None
            # of it ports to sqlite as written, and none of it is needed by the
            # hardware settings tables (virtual gate matrices, AWG attenuations),
            # which create their own tables on demand.
            #
            # So on sqlite the connection is a hardware settings store only.
            # Measurement data must go somewhere else -- e.g. QCodesDataSaver.
            logger.info(
                "sqlite database: hardware settings only, "
                "dataset schema is not created"
            )
            return
        local_database_update_routine(conn)
        sample_info_queries.add_sample(conn)
        conn.commit()

    @classmethod
    def _connect_remote(cls):
        if cls._remote_connection is not None and not getattr(
            cls._remote_connection, "closed", False
        ):
            cls._remote_connection.close()

        if SQL_conn_info_remote.dbname is not None:
            cls._remote_connection = connect_remote_db()
        else:
            raise Exception("No remote database configured")
