import os
import logging

from sqlalchemy import create_engine, URL
from sqlalchemy.orm import sessionmaker, Session

from core_tools.data.sqdl.model import create_database


logger = logging.getLogger(__name__)


class UploaderDb:
    echo_sql = False  # enable for debugging

    def __init__(self, config: dict = None, db_file=None):
        # if db_file is None:
        #     db_file = ':memory:'
        # else:
        #     db_file = os.path.expanduser(db_file)
        #     print(db_file)
        #     os.makedirs(os.path.dirname(db_file), exist_ok=True)
        #
        # self.engine = create_engine("sqlite+pysqlite:///" + db_file,
        #                             echo=UploaderDb.echo_sql,
        #                             )
        if db_file is not None:
            logger.warning("SQDL Uploader no longer uses SQLite: db_file parameter depricated")

        if config is None:
            config = {}

        connection_url = URL.create(
            drivername="postgresql+psycopg2",
            host=config.get("host", default="localhost"),
            port=config.get("port", default=5432),
            username=config.get("username", default="dbijl"),
            database=config.get("database", default="core-tools")
        )

        self.engine = create_engine(
            connection_url,
            echo=UploaderDb.echo_sql,
        )

        create_database(self.engine)
        self.sessionmaker = sessionmaker(bind=self.engine)

    def session(self) -> Session:
        return self.sessionmaker()
