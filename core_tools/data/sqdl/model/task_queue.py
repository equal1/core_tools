import logging
from dataclasses import dataclass

from psycopg2._psycopg import connection as Connection


logger = logging.getLogger(__name__)


@dataclass
class DatasetInfo:
    scope: str
    uid: int
    path: str


@dataclass
class UploadTask:
    idx: int  # defined by database (generated index)
    # REVIEW SdS: version or version_id (sqlalchemy) is the common name when using optimistic locking.
    task_iteration: int
    scope: str | None
    # REVIEW SdS: uid as used in sQDL. If component outside of core-tools it should not call it core-tools.
    coretools_uid: int
    dataset_path: str

    update_dataset: bool = False
    update_name: bool = False
    update_rating: bool = False

    # REVIEW SdS: is_ready is as bad as set_raw_final. Rename to make_raw_data_immutable ?
    is_ready: bool = False
    has_failed: bool = False
    should_retry: bool = False
    is_claimed_by: int | None = None


def get_tasks(conn: Connection) -> list[UploadTask]:
    with conn:
        c = conn.cursor()
        # REVIEW SdS: Define UploadTask.Columns = "idx, task_iteration, ..."
        # or use * and dict_cursor.
        c.execute(
            query="""
                SELECT  idx, task_iteration, scope, coretools_uid, dataset_path, update_dataset, update_name,
                        update_rating, is_ready, has_failed, should_retry, is_claimed_by
                FROM    upload_task_queue
                ;
            """
        )
        results = c.fetchall()
    return [UploadTask(*r) for r in results]


def claim_oldest_task(conn: Connection, pid: int) -> UploadTask | None:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                SELECT      idx, task_iteration, scope, coretools_uid, dataset_path, update_dataset, update_name,
                            update_rating, is_ready, has_failed, should_retry, is_claimed_by
                FROM        upload_task_queue
                WHERE       NOT has_failed AND is_claimed_by IS NULL
                ORDER BY    idx
                LIMIT       1
                ;
            """
        )
        result = c.fetchone()

    if result is None:
        return None

    task = UploadTask(*result)
    if not claim_task(conn, task, pid):
        return None
    return task


def claim_newest_retry_task(conn: Connection, pid: int) -> UploadTask | None:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                SELECT      idx, task_iteration, scope, coretools_uid, dataset_path, update_dataset, update_name,
                            update_rating, is_ready, has_failed, should_retry, is_claimed_by
                FROM        upload_task_queue
                WHERE       should_retry AND is_claimed_by IS NULL
                ORDER BY    idx DESC
                LIMIT 1
                ;
            """,
            vars={
                "pid": pid
            }
        )
        result = c.fetchone()
    if result is None:
        return None

    task = UploadTask(*result)
    if not claim_task(conn, task, pid):
        return None

    return task


def claim_task(conn: Connection, task: UploadTask, pid: int) -> bool:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                UPDATE  upload_task_queue
                SET
                        task_iteration = task_iteration + 1,
                        is_claimed_by = %(pid)s
                WHERE
                        idx = %(idx)s
                AND     task_iteration = %(iter)s
                ;

            """,
            vars={
                "pid": pid,
                "idx": task.idx,
                "iter": task.task_iteration
            }
        )

    if c.rowcount != 1:
        logger.warning(f"Failed to claim task with uid '{task.coretools_uid}'")
        return False
    task.task_iteration += 1
    return True


def release_task(conn: Connection, task: UploadTask) -> None:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                UPDATE  upload_task_queue
                SET     is_claimed_by = NULL
                WHERE   idx = %(idx)s
                ;
            """,
            vars={
                "idx": task.idx,
            }
        )
        released = c.rowcount == 1

    if not released:
        logger.warning(f"Failed to release task with uid '{task.coretools_uid}'")


def get_claimed_tasks(conn: Connection) -> list[UploadTask]:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                SELECT  idx, task_iteration, scope, coretools_uid, dataset_path, update_dataset, update_name,
                        update_rating, is_ready, has_failed, should_retry, is_claimed_by
                FROM    upload_task_queue
                WHERE is_claimed_by IS NOT NULL
                ORDER BY idx
                ;
            """
        )
        results = c.fetchall()
    return [UploadTask(*r) for r in results]


def add_dataset(conn: Connection, dsi: DatasetInfo, is_finished: bool = False) -> None:
    # update_dataset = True
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                INSERT INTO upload_task_queue
                    ( task_iteration, scope, coretools_uid, dataset_path, update_dataset, is_ready )
                VALUES
                    ( 1, %(scope)s, %(uid)s, %(path)s, TRUE, %(is_finished)s )
                ON CONFLICT (coretools_uid) DO UPDATE SET
                    task_iteration = excluded.task_iteration + 1,
                    update_dataset = TRUE,
                    is_ready = %(is_finished)s
                ;
            """,
            vars={
                "scope": dsi.scope,
                "uid": dsi.uid,
                "path": dsi.path,
                "is_finished": is_finished
            }
        )


def update_dataset(conn: Connection, dsi: DatasetInfo, is_finished: bool = False) -> None:
    # update_dataset = True
    # has_failed = False
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                INSERT INTO upload_task_queue
                    ( task_iteration, scope, coretools_uid, dataset_path, update_dataset, has_failed, is_ready )
                VALUES
                    ( 1, %(scope)s, %(uid)s, %(path)s, TRUE, FALSE, %(is_finished)s )
                ON CONFLICT (coretools_uid) DO UPDATE SET
                    task_iteration = excluded.task_iteration + 1,
                    update_dataset = TRUE,
                    has_failed = FALSE,
                    is_ready = %(is_finished)s
                ;
            """,
            vars={
                "scope": dsi.scope,
                "uid": dsi.uid,
                "path": dsi.path,
                "is_finished": is_finished
            }
        )


def reload_dataset(conn: Connection, dsi: DatasetInfo, is_finished: bool = False) -> None:
    # update_dataset = True
    # should_retry = True
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                INSERT INTO upload_task_queue
                    ( task_iteration, scope, coretools_uid, dataset_path, update_dataset, should_retry, is_ready )
                VALUES
                    ( 1, %(scope)s, %(uid)s, %(path)s, TRUE, TRUE, %(is_finished)s )
                ON CONFLICT (coretools_uid) DO UPDATE SET
                    task_iteration = excluded.task_iteration + 1,
                    update_dataset = TRUE,
                    should_retry = TRUE,
                    is_ready = %(is_finished)s
                ;
            """,
            vars={
                "scope": dsi.scope,
                "uid": dsi.uid,
                "path": dsi.path,
                "is_finished": is_finished
            }
        )


def update_name(conn: Connection, dsi: DatasetInfo) -> None:
    # update_name = True
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                INSERT INTO upload_task_queue
                    ( task_iteration, scope, coretools_uid, dataset_path, update_name )
                VALUES
                    ( 1, %(scope)s, %(uid)s, %(path)s, TRUE )
                ON CONFLICT (coretools_uid) DO UPDATE SET
                    task_iteration = excluded.task_iteration + 1,
                    update_name = TRUE
                ;
            """,
            vars={
                "scope": dsi.scope,
                "uid": dsi.uid,
                "path": dsi.path,
            }
        )


def update_rating(conn: Connection, dsi: DatasetInfo) -> None:
    # update_rating = True
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                INSERT INTO upload_task_queue
                    ( task_iteration, scope, coretools_uid, dataset_path, update_rating )
                VALUES
                    ( 1, %(scope)s, %(uid)s, %(path)s, TRUE )
                ON CONFLICT (coretools_uid) DO UPDATE SET
                    task_iteration = excluded.task_iteration + 1,
                    update_rating = TRUE
                ;
            """,
            vars={
                "scope": dsi.scope,
                "uid": dsi.uid,
                "path": dsi.path,
            }
        )


def delete_task(conn: Connection, task: UploadTask) -> bool:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                DELETE FROM upload_task_queue
                WHERE       idx = %(idx)s
                AND         task_iteration = %(iter)s
                ;
            """,
            vars={
                "idx": task.idx,
                "iter": task.task_iteration
            }
        )
        deleted = c.rowcount == 1
    return deleted


def get_all_failed_tasks(conn: Connection) -> list[UploadTask]:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
            SELECT
                idx, task_iteration, scope, coretools_uid, dataset_path, update_dataset, update_name, update_rating, is_ready, has_failed, should_retry, is_claimed_by
            FROM        upload_task_queue
            WHERE       has_failed
            ORDER BY    idx
            """
        )
        result = c.fetchall()
    return [UploadTask(*r) for r in result]


def set_failed(conn: Connection, task: UploadTask) -> None:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                UPDATE  upload_task_queue
                SET
                        task_iteration = task_iteration + 1,
                        has_failed = TRUE,
                        should_retry = FALSE,
                        is_claimed_by = NULL
                WHERE
                        idx = %(idx)s
                AND     task_iteration = %(iter)s
                ;
            """,
            vars={
                "idx": task.idx,
                "iter": task.task_iteration
            }
        )
        to_be_released = c.rowcount == 0
    if to_be_released:
        release_task(conn, task)


def retry_all_failed(conn: Connection) -> None:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                UPDATE  upload_task_queue
                SET
                        task_iteration = task_iteration + 1,
                        should_retry = TRUE
                WHERE
                        has_failed = TRUE
                ;
            """,
            vars={
            }
        )


def get_counts(conn: Connection) -> dict[str, int]:
    with conn:
        c = conn.cursor()
        c.execute(
            query="""
                SELECT failed, retry, COUNT(*)
                FROM upload_task_queue
                GROUP BY failed, retry
                ;
            """
        )
        records = c.fetchall()

    result = {}
    for failed, retry, count in records:
        result[(failed, retry)] = count
    return {
        "new": result.get((False, False), default=0),
        "reload": result.get((False, True), default=0),
        "failed": result.get((True, False), default=0),
        "retry": result.get((True, True), default=0)
    }
