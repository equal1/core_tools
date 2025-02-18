from psycopg2._psycopg import cursor as Cursor


def read(c: Cursor) -> str:
    """
    """
    query = """
        SELECT major, minor, patch
        FROM coretools_version;
    """
    c.execute(query=query)
    record = c.fetchall()
    assert len(record) == 1, "Either no or more that one database version exists"
    return "{}.{}.{}".format(*record[0])
