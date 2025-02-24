from typing import List

from psycopg2._psycopg import connection as Connection


def get_data_to_sync(conn: Connection) -> List[int]:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                SELECT uuid
                FROM global_measurement_overview
                WHERE NOT data_synchronized
                ;
            """
        )
        records = c.fetchall()
    return [r[0] for r in records]


def get_table_to_sync(conn: Connection) -> List[int]:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                SELECT uuid
                FROM global_measurement_overview
                WHERE NOT table_synchronized
                ;
            """
        )
        records = c.fetchall()
    return [r[0] for r in records]


def set_data_as_synced(conn: Connection, ct_uid: int) -> bool:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                UPDATE global_measurement_overview
                SET data_synchronized = TRUE
                WHERE uuid = %(uid)s;
            """,
            vars={
                "uid": ct_uid
            }
        )
        synced = c.rowcount == 1
    return synced


def set_table_as_synced(conn: Connection, ct_uid: int) -> bool:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                UPDATE global_measurement_overview
                SET table_synchronized = TRUE
                WHERE uuid = %(uid)s;
            """,
            vars={
                "uid": ct_uid
            }
        )
        synced = c.rowcount == 1
    return synced
