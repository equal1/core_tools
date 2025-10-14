import logging
import sqlite3

import psycopg2

from core_tools.data.SQL.connect import SQL_conn_info_local, SQL_conn_info_remote

logger = logging.getLogger(__name__)


def connect_local_db():
    if SQL_conn_info_local.dbname is None:
        raise Exception("No local database configured")
    try:
        if getattr(SQL_conn_info_local, "is_sqlite", False):
            conn = sqlite3.connect(
                database=SQL_conn_info_local.dbname,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            conn.isolation_level = "DEFERRED"
            return conn
        return psycopg2.connect(
            dbname=SQL_conn_info_local.dbname,
            user=SQL_conn_info_local.user,
            password=SQL_conn_info_local.passwd,
            host=SQL_conn_info_local.host,
            port=SQL_conn_info_local.port,
            gssencmode="disable",
        )
    except Exception:
        logger.error("Failed to connect to local database", exc_info=True)
        raise Exception("Failed to connect to local database")


def connect_remote_db():
    if SQL_conn_info_remote.dbname is None:
        raise Exception("No remote database configured")
    try:
        if getattr(SQL_conn_info_remote, "is_sqlite", False):
            conn = sqlite3.connect(
                database=SQL_conn_info_remote.dbname,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            conn.isolation_level = "DEFERRED"
            return conn
        return psycopg2.connect(
            dbname=SQL_conn_info_remote.dbname,
            user=SQL_conn_info_remote.user,
            password=SQL_conn_info_remote.passwd,
            host=SQL_conn_info_remote.host,
            port=SQL_conn_info_remote.port,
            gssencmode="disable",
        )
    except Exception:
        logger.error("Failed to connect to remote database", exc_info=True)
        raise Exception("Failed to connect to remote database")
