from core_tools.data.SQL.SQL_connection_mgr import (
    SQL_database_manager as DatabaseManager
)
from core_tools.data.SQL.model import version


def get_setting(parameter: str) -> str | None:
    with DatabaseManager().conn_local as cursor:
        cursor.execute(
            sql="""
                SELECT value FROM settings WHERE parameter = ?
            """,
            parameters=(parameter,)
        )
        value = cursor.fetchone()
    return value


def set_setting(parameter: str, value: str):
    with DatabaseManager().conn_local as cursor:
        cursor.execute(
            """
                INSERT OR REPLACE INTO settings (parameter, value) VALUES (?, ?)
            """,
            (parameter, value)
        )


def clear_setting(parameter: str):
    with DatabaseManager().conn_local as cursor:
        cursor.execute(
            """
                DELETE FROM settings WHERE parameter = ?
            """,
            (parameter,)
        )


def get_database_version(assert_requirement=False) -> str:
    version.get_database_version(
        DatabaseManager().conn_local,
        assert_requirement
    )
