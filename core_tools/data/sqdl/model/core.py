from dataclasses import dataclass
from typing import List, Optional

from psycopg2._psycopg import connection as Connection


@dataclass
class MeasurementInfo:
    coretools_uid: int
    sqdl_uuid: str

    scope: str
    experiment_name: str
    starred: bool
    completed: bool


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


def get_measurement_info(conn: Connection, coretools_uid: int) -> Optional[MeasurementInfo]:
    statement = """
        SELECT overview.uuid, datasets.sqdl_uuid, overview.scope, overview.exp_name, overview.starred, overview.completed
        FROM global_measurement_overview AS overview
        JOIN sqdl_dataset AS datasets
        ON overview.uuid = datasets.coretools_uid
        WHERE overview.uuid = %(ct-uid)s;
    """
    parameters = {
        "ct-uid": coretools_uid
    }

    with conn:
        cur = conn.cursor()
        cur.execute(
            query=statement,
            vars=parameters,
        )
        result = cur.fetchone()

    if result is not None:
        return MeasurementInfo(*result)
    return None
