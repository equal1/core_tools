import logging
from dataclasses import dataclass
from typing import List

from sqlalchemy import select, delete, update, func
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqdl_coretools_sync.uploader.model import UploadTask
from sqdl_coretools_sync.uploader.uploader_db import UploaderDb


logger = logging.getLogger(__name__)


@dataclass
class DatasetLocator:
    scope: str
    uid: int
    path: str


class UploaderTaskQueue:

    def __init__(self, db: UploaderDb):
        self.db = db

    def get_tasks(self) -> list[UploadTask]:
        with self.db.session() as session:
            stmt = select(UploadTask)
            result = session.scalars(stmt).all()
            return result

    def get_oldest_task(self, pid: int) -> UploadTask:
        with self.db.session() as session:
            stmt = select(UploadTask).where(~UploadTask.failed & UploadTask.claimed_by.is_(None))
            stmt = stmt.order_by(UploadTask.id)
            stmt = stmt.limit(1)
            task = session.scalars(stmt).first()
            if task is None:
                return None
        if not self.claim_task(task, pid):
            return None
        return task

    def get_newest_retry_task(self, pid: int) -> UploadTask:
        with self.db.session() as session:
            stmt = select(UploadTask).where(UploadTask.retry & UploadTask.claimed_by.is_(None))
            stmt = stmt.order_by(UploadTask.id.desc())
            stmt = stmt.limit(1)
            task = session.scalars(stmt).first()
            if task is None:
                return None
        if not self.claim_task(task, pid):
            return None
        return task

    def claim_task(self, task: UploadTask, pid: int) -> bool:
        with self.db.session() as session:
            stmt = update(UploadTask).values(
                version_id=UploadTask.version_id + 1,
                claimed_by=pid,
            ).where((UploadTask.id == task.id) & (UploadTask.version_id == task.version_id))
            update_result = session.execute(stmt).rowcount
            session.commit()
            if update_result != 1:
                logger.info(f"Failed to claim task uid {task.uid}")
                return False
            task.version_id += 1
            return True

    def get_claimed_tasks(self) -> List[UploadTask]:
        with self.db.session() as session:
            stmt = select(UploadTask).where(UploadTask.claimed_by.is_not(None))
            stmt = stmt.order_by(UploadTask.id)
            return session.scalars(stmt).all()

    def release_task(self, task):
        with self.db.session() as session:
            stmt = update(UploadTask).values(
                claimed_by=None,
            ).where(UploadTask.id == task.id)
            update_result = session.execute(stmt).rowcount
            session.commit()
            if update_result != 1:
                logger.warning(f"Failed to release task uid {task.uid}")

    def list_all_failed(self) -> UploadTask:
        with self.db.session() as session:
            stmt = select(UploadTask).where(UploadTask.failed)
            stmt = stmt.order_by(UploadTask.id)
            return session.scalars(stmt).all()

    def add_dataset(self, ds_locator: DatasetLocator, final=False) -> None:
        self._insert_or_update_task(ds_locator, update_dataset=True, set_raw_final=final)

    def update_dataset(self, ds_locator: DatasetLocator, final=False) -> None:
        self._insert_or_update_task(ds_locator, update_dataset=True, set_raw_final=final,
                                    failed=False)

    def reload_dataset(self, ds_locator: DatasetLocator, final=False) -> None:
        self._insert_or_update_task(ds_locator, update_dataset=True, set_raw_final=final, retry=True)

    def update_name(self, ds_locator: DatasetLocator) -> None:
        self._insert_or_update_task(ds_locator, update_name=True)

    def update_rating(self, ds_locator: DatasetLocator):
        self._insert_or_update_task(ds_locator, update_rating=True)

    def delete_task(self, task) -> bool:
        with self.db.session() as session:
            stmt = delete(UploadTask).where(
                (UploadTask.id == task.id) & (UploadTask.version_id == task.version_id))
            delete_result = session.execute(stmt)
            deleted = delete_result.rowcount == 1
            session.commit()
        return deleted

    def set_failed(self, task) -> None:
        with self.db.session() as session:
            stmt = update(UploadTask).values(
                version_id=UploadTask.version_id + 1,
                failed=True,
                retry=False,
                claimed_by=None,
            ).where(
                (UploadTask.id == task.id) & (UploadTask.version_id == task.version_id))
            update_result = session.execute(stmt).rowcount
            session.commit()
        if not update_result:
            self.release_task(task)

    def retry_all_failed(self) -> None:
        with self.db.session() as session:
            stmt = update(UploadTask).values(
                version_id=UploadTask.version_id + 1,
                retry=True,
            ).where(UploadTask.failed)
            session.execute(stmt)
            session.commit()

    def _insert_or_update_task(self, ds_locator: DatasetLocator, **kwargs) -> None:
        scope = ds_locator.scope
        uid = ds_locator.uid
        path = ds_locator.path
        with self.db.session() as session:
            stmt = sqlite_upsert(UploadTask).values(version_id=1, scope=scope, uid=uid, ds_path=path, **kwargs)
            stmt = stmt.on_conflict_do_update(
                set_=dict(version_id=UploadTask.version_id + 1, **kwargs))
            session.execute(stmt)
            session.commit()

    def get_counts(self) -> dict[str, int]:
        counts = {}
        with self.db.session() as session:
            stmt = select(UploadTask.failed, UploadTask.retry, func.count()).select_from(UploadTask)
            stmt = stmt.group_by(UploadTask.failed, UploadTask.retry)
            results = {}
            for failed, retry, count in session.execute(stmt).all():
                results[(failed, retry)] = count
            counts["new"] = results.get((False, False), 0)
            counts["reload"] = results.get((False, True), 0)
            counts["failed"] = results.get((True, False), 0)
            counts["retry"] = results.get((True, True), 0)
            return counts


if __name__ == "__main__":
    db = UploaderDb('~/.sqdl_uploader/uploader-test.db')
    uploader = UploaderTaskQueue(db)

    print(uploader.get_tasks())

    uploader.add_dataset(1234, 'somewhere')
    uploader.add_dataset(1235, 'else')
    uploader.add_dataset(1299, 'there')
    uploader._insert_or_update_task(1234, 'somewhere', failed=False, retry=False)
    uploader._insert_or_update_task(1235, 'else', failed=False, retry=False)
    uploader._insert_or_update_task(1299, 'there', failed=False, retry=False)

    uploader.update_dataset(1234, 'somewhere')
    uploader.update_dataset(1235, 'else', final=True)
    print('All:', uploader.get_tasks())

    print('Fail:', uploader.get_oldest_task())
    task = uploader.get_oldest_task()
    uploader.set_failed(task)
    print('Delete', uploader.get_oldest_task())
    task = uploader.get_oldest_task()
    uploader.delete_task(task)

    print('All:', uploader.get_tasks())

    print('Update', uploader.get_oldest_task())
    task = uploader.get_oldest_task()
    uploader.update_rating(task.uid, task.ds_path)
    uploader.update_name(task.uid, task.ds_path)
    print(uploader.get_tasks())

    uploader.delete_task(task)
    print('After delete', uploader.get_tasks())
