from core_tools.data.SQL.connect import set_up_local_storage
from core_tools.data.SQL.db_connections import connect_local_db
from core_tools.data.SQL.SQL_common_commands import execute_statement, execute_query


def main():
    """Demonstrate using an in-memory SQLite database."""
    set_up_local_storage(
        user="",
        passwd="",
        dbname=":memory:",
        project="demo",
        set_up="memory",
        sample="sample",
        is_sqlite=True,
    )
    conn = connect_local_db()

    execute_statement(
        conn,
        "CREATE TABLE demo_table (id INTEGER PRIMARY KEY, value TEXT)",
    )
    execute_statement(
        conn,
        "INSERT INTO demo_table (value) VALUES (%s)",
        ("memory",),
    )
    conn.commit()

    rows = execute_query(conn, "SELECT id, value FROM demo_table")
    print(rows)

    conn.close()


if __name__ == "__main__":
    main()
