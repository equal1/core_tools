from core_tools.data.sqdl.model import UploadLog
from core_tools.data.sqdl.uploader_db import UploaderDb


class UploadLogger:

    def __init__(self, db: UploaderDb):
        self.db = db

    def log(self, scope, ds_uid, message):
        with self.db.session() as session:
            session.add(
                UploadLog(
                    scope=scope,
                    ds_uid=ds_uid,
                    message=message
                )
            )
            session.commit()
