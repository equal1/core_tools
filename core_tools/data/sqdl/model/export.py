import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core_tools.data.SQL.SQL_connection_mgr import (
    SQL_database_manager as DatabaseManager
)

from psycopg2._psycopg import connection as Connection, cursor as Cursor
from psycopg2.extras import RealDictCursor
from psycopg2 import sql


logger = logging.getLogger(__name__)


@dataclass
class SyncStatus:
    is_new: bool
    changed_name: bool = False
    changed_rating: bool = False
    is_complete: bool = False


@dataclass
class ExportAction:
    uuid: int
    data_changed: bool = False
    completed: bool = False
    update_star: bool = False
    update_name: bool = False
    resume_after: datetime | None = None
    data_modify_count: int = 0


@dataclass
class MeasurementInfo:
    coretools_uid: int
    sqdl_uuid: str

    scope: str
    experiment_name: str
    starred: bool
    completed: bool


def get_data_for_export() -> dict | None:
    """
    """
    with DatabaseManager().conn_local as conn:
        c: Cursor = conn.cursor(cursor_factory=RealDictCursor)
        c.execute(
            query="""
                SELECT      *
                FROM        global_measurement_overview
                WHERE       NOT data_synchronized
                    OR      NOT table_synchronized
                ORDER BY    data_synchronized,
                            uuid
                LIMIT       1
            """
        )
        result = c.fetchone()
    return result


def set_export_synchronized(action: ExportAction, name: str, rating: bool) -> tuple[bool, bool]:
    """
    Register data and meta-data as synchronized if their values have not changed
    since Export start.

    :param action: The export action to resolve.
    :param name: The measurement name to be updated.
    :param rating: The measurement rating to be updated.
    :returns: Two boolean values, indicating successful synchronization for data
        and metadata, respectively.
    """
    with DatabaseManager().conn_local as conn:
        c: Cursor = conn.cursor()
        c.execute(
            query="""
                UPDATE  global_measurement_overview
                SET     data_synchronized = TRUE
                WHERE   uuid = %(uid)s
                    AND data_update_count = %(update_count)s
            """,
            vars={
                'uid': action.uuid,
                'update_count': action.data_modify_count,
            }
        )
        data_synced = c.rowcount == 1

        c.execute(
            query="""
                UPDATE  global_measurement_overview
                SET     table_synchronized = TRUE
                WHERE   uuid = %(uid)s
                    AND exp_name = %(name)s
                    AND starred = %(rating)s
            """,
            vars={
                'uid': action.uuid,
                'name': name,
                'rating': rating,
            }
        )
        table_synced = c.rowcount == 1
    return data_synced, table_synced


def get_expired_export_action(expiration_time: datetime) -> ExportAction | None:
    with DatabaseManager().conn_local as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            query="""
                SELECT uuid
                FROM coretools_exported
                WHERE       raw_final = False
                    AND     measurement_start_time < %(expiration_time)s
                    AND     export_state = 1
                ORDER BY uuid
                LIMIT 1
            """,
            vars={
                "expiration_time": expiration_time
            },
        )
        data = cursor.fetchone()
    if data:
        return ExportAction(data['uuid'], completed=True)
    else:
        return None


def set_exported(measurement, path: str, is_complete: bool = False) -> None:
    uuid = measurement.exp_uuid
    start_time = measurement.run_timestamp
    completed = measurement.completed or is_complete

    with DatabaseManager().conn_local as conn:
        cursor = conn.cursor()
        cursor.execute(
            query="""
                INSERT INTO coretools_exported
                    ( uuid, measurement_start_time, path, export_state, raw_final )
                VALUES
                    ( %(uuid)s, %(start_time)s, %(path)s, %(export_state)s, %(raw_final)s )
                ON CONFLICT (uuid) DO UPDATE
                SET
                    uuid = %(uuid)s,
                    measurement_start_time = %(start_time)s,
                    path = %(path)s,
                    export_state = %(export_state)s,
                    raw_final = %(raw_final)s

            """,
            vars={
                "uuid": uuid,
                "start_time": start_time,
                "path": path,
                "export_state": 1,
                "raw_final": completed,
            }
        )


def set_export_error(uuid, message, code=99) -> None:
    with DatabaseManager().conn_local as conn:
        cursor = conn.cursor()
        cursor.execute(
            query="""
                INSERT INTO coretools_exported
                    ( uuid, export_state, export_errors )
                VALUES
                    ( %(uuid)s, %(export_state)s, %(export_errors)s )
                ON CONFLICT (uuid) DO UPDATE
                SET
                    uuid = %(uuid)s,
                    export_state = %(export_state)s,
                    export_errors = %(export_errors)s

            """,
            vars={
                "uuid": uuid,
                "export_state": code,
                "export_errors": message,
            }
        )


def get_failed_exports() -> list[tuple[int, bool]]:
    with DatabaseManager().conn_local as conn:
        cursor = conn.cursor()
        cursor.execute(
            query="""
                SELECT uuid, raw_final
                FROM coretools_exported
                WHERE export_state BETWEEN 10 AND 100
                ORDER BY uuid
                ;
            """
        )
        records = cursor.fetchall()
    return records


# review todo: add generic 'get X from Y for Z' query option
# covers both get_scope and get_measurement_info implementations
def get_measurement_scope(uid: int) -> dict[str, str] | None:
    """
    Get a measurements scope and project values.

    :param uid: Measurement UID from the core-tools database.
    :returns: A dictionary containing scope and project parameters, if the
        measurement exists.
    """
    statement = """
        SELECT scope, project FROM global_measurement_overview WHERE uuid = %(ct-uid)s;
    """
    parameters = {
        "ct-uid": uid
    }

    with DatabaseManager().conn_local as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            query=statement,
            vars=parameters
        )
        result = cur.fetchone()
    return result


# review todo: replace with generated select query
def get_measurement_completed(uid: int) -> bool | None:
    statement = """
            SELECT completed FROM global_measurement_overview WHERE uuid = %(uid)s
        """
    with DatabaseManager().conn_local as conn:
        cursor = conn.cursor()
        cursor.execute(
            statement,
            vars={
                "uid": uid
            }
        )
        result = cursor.fetchone()
    return result


# review todo: only used for completed parameter
# def get_measurement_info(coretools_uid: int) -> MeasurementInfo | None:
#     statement = """
#         SELECT overview.uuid, datasets.sqdl_uuid, overview.scope, overview.exp_name, overview.starred, overview.completed
#         FROM global_measurement_overview AS overview
#         LEFT JOIN sqdl_dataset AS datasets
#         ON overview.uuid = datasets.coretools_uid
#         WHERE overview.uuid = %(ct-uid)s;
#     """
#     parameters = {
#         "ct-uid": coretools_uid
#     }
#
#     with DatabaseManager().conn_local as conn:
#         cur = conn.cursor()
#         cur.execute(
#             query=statement,
#             vars=parameters,
#         )
#         result = cur.fetchone()
#
#     if result is not None:
#         return MeasurementInfo(*result)
#     return None


def execute_generic_select_query(
        select_columns: list[str],
        from_table: str,
        where_equal_conditions: dict[str, Any] | None = None,
        limit: int | None = None,
) -> Any | None:
    """
    Query builder for generic SELECT queries.

    :param select_columns: List of column names to select.
    :param from_table: Name of the table from which to select.
    :param where_equal_conditions: Collection of key-value pairs used to filter
        specified columns (keys) on containing a specific value (values).
        Concatenated together using AND logic operator.
    """

    # basic SELECT query
    query = sql.SQL("SELECT {fields} FROM {table} ").format(
        fields=sql.SQL(", ").join(select_columns),
        table=sql.Identifier(from_table)
    )

    # extend query with WHERE conditions
    if where_equal_conditions is not None:
        where_section = sql.SQL(" WHERE {conditions} ").format(
            conditions=sql.SQL(" AND ").join(
                [
                    sql.SQL(" {key} == {placeholder} ").format(
                        key=sql.Identifier(key),
                        placeholder=sql.Placeholder(key)
                    )
                    for key
                    in where_equal_conditions.keys()
                ]
            )
        )
        query = sql.Composed([
            query,
            where_section,
        ])

    # extend query with LIMIT
    if limit is not None:
        query = sql.Composed([
            query,
            sql.SQL(" LIMIT {limit_value} ").format(limit_value=limit)
        ])

    with DatabaseManager().conn_local as conn:
        cursor = conn.cursor()
        cursor.execute(
            query,
            vars=where_equal_conditions,
        )
