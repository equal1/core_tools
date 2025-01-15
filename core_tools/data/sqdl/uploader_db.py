import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from sqdl_coretools_sync.uploader.model import create_database


class UploaderDb:
    echo_sql = False  # enable for debugging

    def __init__(self, db_file=None):
        if db_file is None:
            db_file = ':memory:'
        else:
            db_file = os.path.expanduser(db_file)
            print(db_file)
            os.makedirs(os.path.dirname(db_file), exist_ok=True)

        self.engine = create_engine("sqlite+pysqlite:///" + db_file,
                                    echo=UploaderDb.echo_sql,
                                    )

        create_database(self.engine)
        self.sessionmaker = sessionmaker(bind=self.engine)

    def session(self) -> Session:
        return self.sessionmaker()
