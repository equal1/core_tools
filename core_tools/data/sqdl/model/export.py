from dataclasses import dataclass
from typing import Optional
from datetime import timedelta as TimeDelta

from psycopg2._psycopg import cursor as Cursor


@dataclass
class SyncStatus:
    is_new: bool
    changed_name: bool = False
    changed_rating: bool = False
    is_complete: bool = False


@dataclass
class ExportAction:
    pass


def export_new_measurement(c: Cursor, ct_uid: int, is_complete: bool):
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


def export_changed_measurement(c: Cursor, ct_uid: int, meta: SyncStatus):
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


def export_changed_data(c: Cursor, ct_uid: int):
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


def get_export_action(c: Cursor) -> Optional[ExportAction]:
    raise NotImplementedError()


def uuid_exists(c: Cursor, uuid) -> bool:
    raise NotImplementedError()


def get_expired_measurement_action(c: Cursor) -> Optional[ExportAction]:
    raise NotImplementedError()


def set_export_error(c: Cursor, uuid, exception, code=99) -> None:
    raise NotImplementedError()


def set_exported(c: Cursor, measurement, path: str, is_complete: bool = False) -> None:
    raise NotImplementedError()


def set_resume_after(c: Cursor, action: ExportAction, wait_time: TimeDelta) -> None:
    raise NotImplementedError()


def increment_fail_count(c: Cursor, action: ExportAction) -> None:
    raise NotImplementedError()


def retry_failed_exports(c: Cursor) -> None:
    c.execute(
        query="""
            SELECT uuid, gg
            FROM coretools_exported
            WHERE export_state BETWEEN 10 AND 100
            ORDER BY uuid
            ;
        """
    )
    records = c.fetchall()
    if len(records) == 0:
        return None
    raise NotImplementedError()
