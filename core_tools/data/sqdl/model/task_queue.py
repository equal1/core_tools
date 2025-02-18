import logging
from typing import Optional, List, Dict
from dataclasses import dataclass

from psycopg2._psycopg import cursor as Cursor


logger = logging.getLogger(__name__)


@dataclass
class DatasetInfo:
    scope: str
    uid: int
    path: str


@dataclass
class UploadTask:
    idx: int  # defined by database (generated index)
    task_iteration: int
    scope: Optional[str]
    coretools_uid: int
    dataset_path: str

    update_dataset: bool = False
    update_name: bool = False
    update_rating: bool = False

    is_ready: bool = False
    has_failed: bool = False
    should_retry: bool = False
    is_claimed_by: Optional[int] = None


def get_tasks(c: Cursor) -> List[UploadTask]:
    c.execute(
        query="""
            SELECT  idx, task_iteration, scope, coretools_uid, dataset_path, update_dataset, update_name, update_rating, is_ready, has_failed, should_retry, is_claimed_by
            FROM    upload_task_queue
            ;
        """
    )
    results = c.fetchall()
    return [UploadTask(*r) for r in results]


def claim_oldest_task(c: Cursor, pid: int) -> Optional[UploadTask]:
    c.execute(
        query="""
            SELECT      idx, task_iteration, scope, coretools_uid, dataset_path, update_dataset, update_name, update_rating, is_ready, has_failed, should_retry, is_claimed_by
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
    if not claim_task(c, task, pid):
        return None

    return task


def claim_newest_retry_task(c: Cursor, pid: int) -> Optional[UploadTask]:
    c.execute(
        query="""
            SELECT      idx, task_iteration, scope, coretools_uid, dataset_path, update_dataset, update_name, update_rating, is_ready, has_failed, should_retry, is_claimed_by
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
    if not claim_task(c, task, pid):
        return None

    return task


def claim_task(c: Cursor, task: UploadTask, pid: int) -> bool:
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
        logger.warning("Failed to claim task with uid '{}'".format(task.coretools_uid))
        return False
    task.task_iteration += 1
    return True


def release_task(c: Cursor, task: UploadTask) -> None:
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

    if c.rowcount != 1:
        logger.warning("Failed to release task with uid '{}'".format(task.coretools_uid))


def get_claimed_tasks(c: Cursor) -> List[UploadTask]:
    c.execute(
        query="""
            SELECT  idx, task_iteration, scope, coretools_uid, dataset_path, update_dataset, update_name, update_rating, is_ready, has_failed, should_retry, is_claimed_by
            FROM    upload_task_queue
            WHERE is_claimed_by IS NOT NULL
            ORDER BY idx
            ;
        """
    )
    results = c.fetchall()
    return [UploadTask(*r) for r in results]


def add_dataset(c: Cursor, dsi: DatasetInfo, is_finished: bool = False) -> None:
    # update_dataset = True
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


def update_dataset(c: Cursor, dsi: DatasetInfo, is_finished: bool = False) -> None:
    # update_dataset = True
    # has_failed = False
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


def reload_dataset(c: Cursor, dsi: DatasetInfo, is_finished: bool = False) -> None:
    # update_dataset = True
    # should_retry = True
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


def update_name(c: Cursor, dsi: DatasetInfo) -> None:
    # update_name = True
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


def update_rating(c: Cursor, dsi: DatasetInfo) -> None:
    # update_rating = True
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


def delete_task(c: Cursor, task: UploadTask) -> bool:
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
    return c.rowcount == 1


def get_all_failed_tasks(c: Cursor) -> List[UploadTask]:
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


def set_failed(c: Cursor, task: UploadTask) -> None:
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
    if c.rowcount == 0:
        release_task(c, task)


def retry_all_failed(c: Cursor) -> None:
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


def get_counts(c: Cursor) -> Dict[str, int]:
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
