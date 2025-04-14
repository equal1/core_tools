from core_tools.data.SQL.SQL_connection_mgr import (
    SQL_database_manager as DatabaseManager
)


# review todo: create a path from 1.1.0 to 1.2.0
def update_to_1_2_0_from_1_1_0():
    pass

    # add settings
    # export current content of taskqueue to sqlite3
    # drop taskqueue table


# review todo: create a path from 1.0.0 to 1.2.0
def update_to_1_2_0_from_1_0_0():
    with DatabaseManager as conn:
        cursor = conn.cursor()

        cursor.execute(
            query="""
                CREATE TABLE IF NOT EXISTS settings (
                    parameter TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL
                );
            """
        )

        cursor.execute(
            query="""
                CREATE TABLE IF NOT EXISTS coretools_exported (
                   id INT GENERATED ALWAYS AS IDENTITY,
                   uuid BIGINT NOT NULL UNIQUE,
                   path TEXT,
                   measurement_start_time timestamp, -- export raw after timeout and not completed.
                   raw_final BOOLEAN DEFAULT FALSE, -- Set when completed or after timeout.

                   -- export state
                   export_state INT DEFAULT 0, -- (0:todo, 1:done, 99: failed),
                   export_errors TEXT,

                   PRIMARY KEY(id)
                );
            """
        )

        cursor.execute(
            query="""
                CREATE INDEX IF NOT EXISTS coretools_exported_uuid_index ON coretools_exported USING BTREE (uuid);
            """
        )
