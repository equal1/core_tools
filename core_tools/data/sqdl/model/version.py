from psycopg2._psycopg import connection as Connection

# REVIEW SdS: do we want more than just database version in the table? Other configuration..
# Proposal: rename table to settings with key/value pairs. Store version as string.
def read(conn: Connection) -> str:
    """
    """
    query = """
        SELECT major, minor, patch
        FROM database_version;
    """
    with conn:
        c = conn.cursor()
        c.execute(query=query)
        record = c.fetchall()
    assert len(record) == 1, "Either no or more that one database version exists"
    major, minor, patch = record[0]
    return f"{major}.{minor}.{patch}"
