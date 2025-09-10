import os

from core_tools.data.SQL.connect import set_up_local_storage
from core_tools.data.SQL.db_connections import connect_local_db
from core_tools.data.SQL.SQL_common_commands import (
    alter_table,
    execute_query,
    execute_statement,
    insert_row_in_table,
    select_elements_in_table,
    update_table,
)


def run_demo(dbname: str) -> None:
    """Demonstrate basic SQL features on the selected database.

    The demo creates a table, inserts rows, updates data, alters the
    table structure and finally queries the results using the utility
    helpers that mirror the PostgreSQL interface.
    """
    set_up_local_storage(
        user="",
        passwd="",
        dbname=dbname,
        project="demo",
        set_up="example",
        sample="sample",
        is_sqlite=True,
    )
    conn = connect_local_db()

    # Start with a clean table
    execute_statement(conn, "DROP TABLE IF EXISTS demo_table")
    execute_statement(
        conn, "CREATE TABLE demo_table (id INTEGER PRIMARY KEY, value TEXT)"
    )

    # Insert a couple of rows
    insert_row_in_table(conn, "demo_table", ("value",), ("hello",))
    insert_row_in_table(conn, "demo_table", ("value",), ("world",))

    # Obtain ids of inserted rows
    id_rows = execute_query(conn, "SELECT id FROM demo_table ORDER BY id")
    first_id, second_id = [row[0] for row in id_rows]

    # Update one of the rows
    update_table(
        conn, "demo_table", ("value",), ("updated",), condition=("id", first_id)
    )

    # Demonstrate altering the table and storing additional information
    alter_table(conn, "demo_table", ("extra",), ("TEXT",))
    update_table(conn, "demo_table", ("extra",), ("info",), condition=("id", second_id))

    conn.commit()

    # Query the resulting table using a dictionary cursor
    rows = select_elements_in_table(
        conn, "demo_table", ("id", "value", "extra"), dict_cursor=True
    )
    print(f"Results for {dbname}:")
    for row in rows:
        print(row)

    conn.close()


if __name__ == "__main__":
    db_file = os.path.join(os.path.dirname(__file__), "demo.db")
    run_demo(db_file)
    run_demo(":memory:")
