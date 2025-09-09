import os

from core_tools.data.SQL.connect import set_up_local_storage
from core_tools.data.SQL.db_connections import connect_local_db
from core_tools.data.SQL.SQL_common_commands import execute_statement, execute_query


def main():
    """Demonstrate connecting to a file-based SQLite database."""
    db_path = os.path.join(os.path.dirname(__file__), "demo.db")
    set_up_local_storage(
        user="",
        passwd="",
        dbname=db_path,
        project="demo",
        set_up="example",
        sample="sample",
        is_sqlite=True,
    )
    conn = connect_local_db()

    execute_statement(
        conn,
        "CREATE TABLE IF NOT EXISTS demo_table (id INTEGER PRIMARY KEY, value TEXT)",
    )
    execute_statement(
        conn,
        "INSERT INTO demo_table (value) VALUES (%s)",
        ("hello",),
    )
    conn.commit()

    rows = execute_query(conn, "SELECT id, value FROM demo_table")
    print(rows)

    conn.close()


if __name__ == "__main__":
    main()
