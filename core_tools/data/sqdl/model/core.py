from typing import List

from psycopg2._psycopg import cursor as Cursor


def core_method(message: str):
    print("from core: {}".format(message))


class CoreOperations:
    def get_data_to_sync(self, c: Cursor) -> List[int]:
        c.execute(
            query="""
                SELECT uuid
                FROM global_measurement_overview
                WHERE NOT data_synchronized
                ;
            """
        )
        records = c.fetchall()
        return [r[0] for r in records]

    def get_table_to_sync(self, c: Cursor) -> List[int]:
        c.execute(
            query="""
                SELECT uuid
                FROM global_measurement_overview
                WHERE NOT table_synchronized
                ;
            """
        )
        records = c.fetchall()
        return [r[0] for r in records]

    def set_data_as_synced(self, c: Cursor, ct_uid: int) -> bool:
        c.execute(
            query="""
                UPDATE global_measurement_overview
                SET data_synchronized = TRUE
                WHERE uuid = %(uid)s;
            """,
            vars={
                "uid": ct_uid
            }
        )
        return c.rowcount == 1

    def set_table_as_synced(self, c: Cursor, ct_uid: int) -> bool:
        c.execute(
            query="""
                UPDATE global_measurement_overview
                SET table_synchronized = TRUE
                WHERE uuid = %(uid)s;
            """,
            vars={
                "uid": ct_uid
            }
        )
        return c.rowcount == 1
