import logging
from dataclasses import dataclass
from typing import List, Dict, Tuple
from uuid import UUID

from psycopg2._psycopg import cursor as Cursor, IntegrityError


logger = logging.getLogger(__name__)


@dataclass
class SQDLFile:
    index: int  # defined by database (generated index)
    dataset_index: int  # defined by database (foreign key)
    sqdl_uuid: int
    filename: str
    last_modified: int  # unix timestamp in microseconds (st_mtime_ns // 1000)


@dataclass
class SQDLDataset:
    index: int  # defined by database (generated index)
    scope: str
    sqdl_uuid: int
    files: List[SQDLFile]


def create_dataset(c: Cursor, scope: str, ct_uid: int, sqdl_uuid: UUID) -> int:
    """
    Create new dataset entry in the 'sqdl_dataset' table. Return the row index of th new entry. If an entry with the specified UUID already exists, return the row index of the existing entry instead.
    """
    try:
        c.execute(
            query="""
                INSERT INTO sqdl_dataset (
                    scope, coretools_uid, sqdl_uuid
                ) VALUES (
                    %(scope)s, %(uid)s, %(uuid)s
                )
                RETURNING idx;
            """,
            vars={
                "scope": scope,
                "uid": ct_uid,
                "uuid": sqdl_uuid,
            }
        )
        index = c.fetchone()[0]
        return index
    except IntegrityError:
        c.execute(
            query="""
                SELECT idx
                FROM sqdl_dataset
                WHERE sqdl_uuid = %(uuid)s
            """,
            vars={
                "uuid": sqdl_uuid
            }
        )
        index = c.fetchone()[0]
        logger.warning("Dataset with UUID '{}' already exists in table 'sqdl_dataset' at index '{}'.".format(sqdl_uuid, index))
        return index


def get_counts(c: Cursor) -> Dict[str, int]:
    """
    """
    counts = {}
    c.execute(query="SELECT COUNT(idx) FROM sqdl_dataset;")
    counts["uploaded-datasets"] = c.fetchone()[0]

    c.execute(query="SELECT COUNT(idx) FROM sqdl_file;")
    counts["uploaded-files"] = c.fetchone()[0]
    return counts


def get_files_for_dataset(c: Cursor, parent_idx: int) -> List[SQDLFile]:
    """
    Get all the SQDLFile entries associated with the SQDLDataset that has the provided index.
    """
    def parse_row(row: Tuple) -> SQDLFile:
        return SQDLFile(
            index=row[0],
            dataset_index=row[1],
            sqdl_uuid=row[2],
            filename=row[3],
            last_modified=[4]
        )

    c.execute(
        query="""
            SELECT idx, dataset_index, sqdl_uuid, filename, last_modified
            FROM sqdl_file
            WHERE dataset_index = %(parent)s;
        """,
        vars={"parent": parent_idx}
    )
    records = c.fetchall()

    return [parse_row(r) for r in records]


def create_or_update_file(c: Cursor, parent_idx: int, sqdl_uuid: UUID, filename: str, last_modified: int) -> None:
    """
    Create new SQDLFile entry. If entry with UUID already exists, update the last-modified timestamp instead.
    """
    # todo: original uploader registry also updates uuid on conflict, but uuid is at all times the conflicting column, so that should do nothing.
    c.execute(
        query="""
            INSERT INTO sqdl_file (
                dataset_index, sqdl_uuid, filename, last_modified
            ) VALUES (
                %(idx)s, %(uuid)s, %(fn)s, %(lm)s
            ) ON CONFLICT (sqdl_uuid) DO UPDATE SET
                last_modified = %(lm)s
            ;
        """,
        vars={
            "idx": parent_idx,
            "uuid": sqdl_uuid,
            "fn": filename,
            "lm": last_modified,
        }
    )
