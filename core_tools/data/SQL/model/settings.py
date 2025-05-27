from core_tools.data.SQL.SQL_connection_mgr import (
    SQL_database_manager as DatabaseManager
)
from core_tools.data.SQL.model import version


def get_setting(parameter: str) -> str | None:
    with DatabaseManager().connection as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
                SELECT value FROM settings WHERE parameter = %s
            """,
            vars=(parameter,)
        )
        value = cursor.fetchone()
    return value


def set_setting(parameter: str, value: str):
    with DatabaseManager().connection as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
                INSERT INTO settings
                    (parameter, value)
                VALUES
                    (%(parameter)s, %(value)s)
                ON CONFLICT (parameter) DO UPDATE
                SET
                    value = %(value)s
            """,
            vars={
                "parameter": parameter,
                "value": value
            }
        )


def clear_setting(parameter: str):
    with DatabaseManager().connection as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
                DELETE FROM settings WHERE parameter = %s
            """,
            vars=(parameter,)
        )


def get_database_version(assert_requirement=False) -> str:
    version.get_database_version(
        DatabaseManager().connection,
        assert_requirement
    )
