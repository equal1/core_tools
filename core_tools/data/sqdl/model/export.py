from dataclasses import dataclass
from datetime import datetime, timedelta

from psycopg2._psycopg import connection as Connection
from psycopg2.extras import RealDictCursor


@dataclass
class SyncStatus:
    is_new: bool
    changed_name: bool = False
    changed_rating: bool = False
    is_complete: bool = False


@dataclass
class ExportAction:
    uuid: int
    id: int | None = None
    # REVIEW SdS: optimistic locking. Rename to version and start at 1.
    modify_count: int = 0
    new_measurement: bool = False
    data_changed: bool = False
    completed: bool = False
    update_star: bool = False
    update_name: bool = False
    fail_count: int = 0
    resume_after: datetime = None

# REVIEW SdS: original code is clearer about the changes being made to database.
def export_new_measurement(conn: Connection, ct_uid: int, is_complete: bool):
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                INSERT INTO coretools_export_updates (
                    uuid, new_measurement, data_changed, completed
                ) VALUES (
                    %(uid)s, TRUE, TRUE, %(completed)s
                ) ON CONFLICT ( uuid ) DO UPDATE SET
                    modify_count = coretools_export_updates.modify_count + 1,
                    new_measurement = TRUE,
                    completed = %(completed)s;
            """,
            vars={
                "uid": ct_uid,
                "completed": is_complete,
            }
        )


def export_changed_measurement(conn: Connection, ct_uid: int, meta: SyncStatus):
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                INSERT INTO coretools_export_updates (
                    uuid, update_star, update_name, completed
                ) VALUES (
                    %(uuid)s, %(star-changed)s, %(name-changed)s, %(completed)s
                ) ON CONFLICT ( uuid ) DO UPDATE SET
                    modify_count = coretools_export_updates.modify_count + 1,
                    update_star = coretools_export_updates.update_star OR %(star-changed)s,
                    update_name = coretools_export_updates.update_name OR %(name-changed)s,
                    completed = %(completed)s;
            """,
            vars={
                "uuid": ct_uid,
                "star-changed": meta.changed_rating,  # star value in global-overview not equal to new value
                "name-changed": meta.changed_name,  # experiment name value in global-overview not equal to new value
                "completed": meta.is_complete
            }
        )


def export_changed_data(conn: Connection, ct_uid: int):
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                INSERT INTO coretools_export_updates (
                    uuid, data_changed
                ) VALUES (
                    %(uid)s, TRUE
                )
                ON CONFLICT ( uuid ) DO UPDATE SET
                    modify_count = coretools_export_updates.modify_count + 1,
                    data_changed = TRUE
                ;
            """,
            vars={
                "uid": ct_uid
            }
        )


def get_export_action(conn: Connection) -> ExportAction | None:
    with conn:
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute(
            query="""
                SELECT * FROM coretools_export_updates
                WHERE resume_after < %(now)s
                ORDER BY uuid
                LIMIT 1
            """,
            vars={
                "now": datetime.now()
            },
        )
        action_data = c.fetchone()
    if action_data:
        return ExportAction(**action_data)
    else:
        return None


def get_expired_export_action(conn: Connection, expiration_time: datetime) -> ExportAction | None:
    with conn:
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute(
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
        data = c.fetchone()
    if data:
        return ExportAction(data['uuid'], completed=True)
    else:
        return None


def delete_export_action(conn: Connection, action: ExportAction) -> bool:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                DELETE FROM coretools_export_updates
                WHERE       id = %(id)s
                    AND     modify_count = %(modify_count)s
            """,
            vars={
                "id": action.id,
                "modify_count": action.modify_count,
            }
        )
        deleted = c.rowcount > 0
    return deleted


def set_exported(conn: Connection, measurement, path: str, is_complete: bool = False) -> None:
    uuid = measurement.exp_uuid
    start_time = measurement.run_timestamp
    completed = measurement.completed or is_complete

    with conn:
        c = conn.cursor()
        c.execute(
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


def set_resume_after(conn: Connection, action: ExportAction, wait_time: float) -> None:
    now = datetime.now()
    resume_after = now + timedelta(seconds=wait_time)

    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                UPDATE coretools_export_updates
                SET resume_after = %(resume_after)s
                WHERE id = %(id)s
            """,
            vars={
                "id": action.id,
                "resume_after": resume_after,
            }
        )


def set_export_error(conn: Connection, uuid, message, code=99) -> None:
    with conn:
        c = conn.cursor()
        c.execute(
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


def increment_fail_count(conn: Connection, action: ExportAction) -> None:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                UPDATE  coretools_export_updates
                SET     fail_count = fail_count + 1
                WHERE   id = %(id)s
            """,
            vars={
                "id": action.id
            }
        )


def get_failed_exports(conn: Connection) -> list[tuple[int, bool]]:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                SELECT uuid, raw_final
                FROM coretools_exported
                WHERE export_state BETWEEN 10 AND 100
                ORDER BY uuid
                ;
            """
        )
        records = c.fetchall()
    return records


def set_retry_export(conn: Connection, uuid, is_complete: bool) -> None:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                INSERT INTO coretools_export_updates
                    ( uuid, data_changed, completed )
                VALUES
                    ( %(uuid)s, TRUE, %(completed)s )
                ON CONFLICT ( uuid ) DO UPDATE
                SET
                    uuid = %(uuid)s,
                    data_changed = TRUE,
                    completed = %(completed)s
            """,
            vars={
                "uuid": uuid,
                "completed": is_complete
            }
        )
