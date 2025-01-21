from sqlalchemy import select, insert, delete, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as psql_insert

from core_tools.data.sqdl.model import UploadedDataset, UploadedFile
from core_tools.data.sqdl.uploader_db import UploaderDb

# %%


class UploadRegistry:

    def __init__(self, db: UploaderDb):
        self.db = db

    def get_create_dataset(self, sqdl_uuid, scope, uid) -> int:
        try:
            with self.db.session() as session:
                stmt = insert(UploadedDataset).values(sqdl_uuid=sqdl_uuid, scope=scope, uid=uid)
                result = session.scalars(stmt.returning(UploadedDataset.id)).first()
                session.commit()
                return result
        except IntegrityError:
            with self.db.session() as session:
                stmt = select(UploadedDataset.id).where(UploadedDataset.sqdl_uuid == sqdl_uuid)
                return session.scalars(stmt).first()

    def get_files(self, dataset_id) -> list[UploadedFile]:
        with self.db.session() as session:
            stmt = select(UploadedFile).where(UploadedFile.dataset_id == dataset_id)
            return session.scalars(stmt).all()

    def add_update_file(self, dataset_id, file_sqdl_uuid, filename, st_mtime_ns) -> None:
        with self.db.session() as session:
            # stmt = sqlite_upsert(UploadedFile).values(
            stmt = psql_insert(UploadedFile).values(
                dataset_id=dataset_id,
                sqdl_uuid=file_sqdl_uuid,
                filename=filename,
                st_mtime_us=st_mtime_ns // 1000)
            stmt = stmt.on_conflict_do_update(
                constraint="uploaded_file_sqdl_uuid_key",
                set_=dict(sqdl_uuid=file_sqdl_uuid, st_mtime_us=st_mtime_ns // 1000))
            session.execute(stmt)
            session.commit()

    def get_counts(self) -> dict[str, int]:
        counts = {}
        with self.db.session() as session:
            stmt = select(func.count()).select_from(UploadedDataset)
            counts["uploaded datasets"] = session.scalar(stmt)
            stmt = select(func.count()).select_from(UploadedFile)
            counts["uploaded files"] = session.scalar(stmt)
            return counts
