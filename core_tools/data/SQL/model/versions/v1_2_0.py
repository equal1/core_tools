from psycopg2._psycopg import cursor as Cursor


def update_to_1_2_0_from_1_1_0(cursor: Cursor):
    """
    Special case for setups that received 1.1.0 version.
    Default should be going from 1.0.0 to 1.2.0 directly.

    User is expected to export and drop the following tables manually:
    - upload_task_queue
    - sqdl_dataset
    - sqdl_file
    - coretools_export_updates
    - upload_log
    - database_version
    """
    cursor.execute(
        query="""
            CREATE TABLE IF NOT EXISTS settings (
                parameter TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL
            )
        """
    )
    cursor.execute(
        query="""
            ALTER TABLE
                sample_info_overview
            DROP COLUMN IF EXISTS
                scope
        """
    )
    cursor.execute(
        query="""
            ALTER TABLE     coretools_exported
            RENAME COLUMN   raw_final
            TO              make_data_immutable
        """
    )
    cursor.execute(
        query="""
            ALTER TABLE     coretools_exported
            RENAME COLUMN   measurement_start_time
            TO              most_recent_update_time
        """
    )


def update_to_1_2_0_from_1_0_0(cursor: Cursor):
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
               most_recent_update_time timestamp, -- export raw after timeout and not completed.
               make_data_immutable BOOLEAN DEFAULT FALSE, -- Set when completed or after timeout.

               -- export state
               export_state INT DEFAULT 0, -- (0:todo, 1:done, 99: failed),
               export_errors TEXT,

               PRIMARY KEY(id)
            );
        """
    )

    cursor.execute(
        query="""
            CREATE INDEX IF NOT EXISTS
                coretools_exported_uuid_index
            ON
                coretools_exported
            USING BTREE (
                uuid
            )
        """
    )

    cursor.execute(
        query="""
            ALTER TABLE
                global_measurement_overview
            ADD COLUMN IF NOT EXISTS
                scope TEXT DEFAULT NULL
        """
    )
