from psycopg2._psycopg import connection as Connection


def read(conn: Connection) -> str:
    """
    """
    query = """
        SELECT major, minor, patch
        FROM coretools_version;
    """
    with conn:
        c = conn.cursor()
        c.execute(query=query)
        record = c.fetchall()
    assert len(record) == 1, "Either no or more that one database version exists"
    return "{}.{}.{}".format(*record[0])
