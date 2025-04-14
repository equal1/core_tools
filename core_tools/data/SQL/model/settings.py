from core_tools.data.SQL.SQL_connection_mgr import (
    SQL_database_manager as DatabaseManager
)


def get_setting(parameter: str) -> str | None:
    with DatabaseManager() as cursor:
        cursor.execute(
            sql="""
                SELECT value FROM settings WHERE parameter = ?
            """,
            parameters=(parameter,)
        )
        value = cursor.fetchone()
    return value


def set_setting(parameter: str, value: str):
    with DatabaseManager() as cursor:
        cursor.execute(
            """
                INSERT OR REPLACE INTO settings (parameter, value) VALUES (?, ?)
            """,
            (parameter, value)
        )


def clear_setting(parameter: str):
    with DatabaseManager() as cursor:
        cursor.execute(
            """
                DELETE FROM settings WHERE parameter = ?
            """,
            (parameter,)
        )
