from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, ForeignKey, DateTime, Index
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


# declarative base class
class Base(DeclarativeBase):
    pass


class UploadTask(Base):
    __tablename__ = "upload_task"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(nullable=False)
    scope: Mapped[str | None]
    uid: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    ds_path: Mapped[str]
    ''' client-app unique id '''
    update_dataset: Mapped[bool] = mapped_column(default=False)
    ''' dataset is new or has changed '''
    set_raw_final: Mapped[bool] = mapped_column(default=False)
    ''' raw file can be uploaded and finalized '''
    update_name: Mapped[bool] = mapped_column(default=False)
    ''' compare name of dataset with name in SQDL and update '''
    update_rating: Mapped[bool] = mapped_column(default=False)
    ''' compare rating of dataset with rating in SQDL and update '''

    failed: Mapped[bool] = mapped_column(default=False)
    retry: Mapped[bool] = mapped_column(default=False)
    claimed_by: Mapped[Optional[int]] = mapped_column(nullable=True)

    __mapper_args__ = {"version_id_col": version_id}
    __table_args__ = (
        Index('upload_claimed_retry', claimed_by, retry),
        Index('upload_claimed_failed', claimed_by, failed),
    )

    def __repr__(self):
        args = []
        args.append(f'id={self.id}')
        args.append(f'version_id={self.version_id}')
        args.append(f'scope={self.scope}')
        args.append(f'uid={self.uid}')
        args.append(f'ds_path="{self.ds_path}"')
        if self.update_dataset:
            args.append('update_dataset=True')
        if self.set_raw_final:
            args.append('set_raw_final=True')
        if self.update_name:
            args.append('update_name=True')
        if self.update_rating:
            args.append('update_rating=True')
        if self.failed:
            args.append('failed=True')
        if self.retry:
            args.append('retry=True')
        if self.claimed_by:
            args.append(f"claimed_by: {self.claimed_by}")

        return 'UploadTask(' + ', '.join(args) + ')'


class UploadedDataset(Base):
    __tablename__ = "uploaded_dataset"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str]
    uid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sqdl_uuid: Mapped[str] = mapped_column(nullable=False, unique=True)
    files: Mapped[list["UploadedFile"]] = relationship(back_populates="dataset")

    def __repr__(self):
        return f'UploadedDataset(scope={self.scope}, uid={self.uid}, sqld_uuid={self.sqld_uuid})'


class UploadedFile(Base):
    __tablename__ = "uploaded_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("uploaded_dataset.id"), index=True)  # link to dataset
    sqdl_uuid: Mapped[str] = mapped_column(nullable=False, unique=True)
    filename: Mapped[str]
    st_mtime_us: Mapped[int] = mapped_column(BigInteger)
    dataset: Mapped["UploadedDataset"] = relationship(back_populates="files")

    def __repr__(self):
        mtime = datetime.fromtimestamp(self.st_mtime_us / 1e6)
        return f'UploadedFile(filename={self.filename}, mtime={mtime}, sqdl_uuid={self.sqdl_uuid})'


class UploadLog(Base):
    __tablename__ = "upload_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str | None]
    ds_uid: Mapped[int] = mapped_column(BigInteger)
    upload_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    message: Mapped[str]  # new dataset, uploaded files, exception xxx.

    def __repr__(self):
        return f'Log(scope={self.scope}, uid={self.ds_uid}, t={self.upload_time}: {self.message})'


def create_database(engine):
    Base.metadata.create_all(engine)
