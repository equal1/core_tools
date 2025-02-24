from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from psycopg2._psycopg import connection as Connection


@dataclass
class UploadLog:
    index: int  # defined by database (generated index)
    scope: Optional[str]
    ct_uid: int
    upload_time: datetime
    message: str


def log(conn: Connection, scope: str, ct_uid: int, message: str):
    """
    Insert a message into the 'upload_log' table.
    """
    query = """
        INSERT INTO upload_log (
            scope,
            ct_uid,
            upload_timestamp,
            message
        ) VALUES (
            %(scope)s,
            %(uid)s,
            %(ts)s,
            %(msg)s
        );
        """
    values = {
        "scope": scope,
        "uid": ct_uid,
        "ts": datetime.now(),
        "msg": message,
    }
    with conn:
        c = conn.cursor()
        c.execute(query=query, vars=values)
