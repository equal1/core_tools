import logging
from typing import Callable
from packaging.version import Version

from core_tools.data.SQL.model.versions.v1_0_0 import initialise_v1_0_0
from core_tools.data.SQL.model.versions.v1_1_0 import update_to_v1_1_0

from psycopg2._psycopg import (
        connection as Connection,
        cursor as Cursor,
        Error as PGError
)


logger = logging.getLogger(__name__)


UpdateOperation = Callable[[Cursor], None]


class DatabaseVersion(Version):
    def __init__(self, version: str):
        super().__init__(version)
        self.patch = self.micro  # staying consistent with Semantic Versioning naming convention

    def next_patch(self):
        return DatabaseVersion(f"{self.major}.{self.minor}.{self.patch + 1}")

    def next_minor(self):
        return DatabaseVersion(f"{self.major}.{self.minor + 1}.0")

    def next_major(self):
        return DatabaseVersion(f"{self.major + 1}.0.0")


__REQUIRED_DATABASE_VERSION__ = DatabaseVersion("1.1.0")


__UPDATE_PATH__: dict[DatabaseVersion, UpdateOperation] = {
    DatabaseVersion("1.1.0"): update_to_v1_1_0,
}


def local_database_update_routine(conn: Connection):
    version = get_database_version(conn, False)

    if version.major == 0:
        with conn:
            cursor = conn.cursor()
            initialise_v1_0_0(cursor)
        version = DatabaseVersion("1.0.0")

    if version < __REQUIRED_DATABASE_VERSION__:
        logger.warning(
            f"Expected local database version {__REQUIRED_DATABASE_VERSION__}, "
            f"but found {version}. Performing updates. This can take a while, depending on the setup."
        )

    while version < __REQUIRED_DATABASE_VERSION__:
        version = _update_database(conn, version)


def get_database_version(
        connection: Connection,
        assert_requirement: bool
) -> DatabaseVersion:
    try:
        with connection:
            cursor = connection.cursor()
            version_str = get_version_setting(cursor)
        version = DatabaseVersion(version_str)
    except PGError as err:
        if err.pgcode == "42P01":
            # 42P01 is the psycopg2 error code for UndefinedTable
            if check_for_v110_case(connection):
                version = DatabaseVersion("1.1.0")
            else:
                version = DatabaseVersion("0.0.0")
                logger.warning("No table 'settings' found, returning v0.0.0")
        else:
            raise err

    if assert_requirement:
        message = (
            "Local database is not up to date "
            f"(expected '{__REQUIRED_DATABASE_VERSION__}', found '{version}'). "
            "Cannot sync to SQDL."
        )
        assert version == __REQUIRED_DATABASE_VERSION__, message

    return version


def check_for_v110_case(conn: Connection) -> bool:
    try:
        with conn:
            conn.cursor().execute("SELECT * FROM database_version")
    except PGError as err:
        if err.pgcode == "42P01":
            return False
        raise err
    return True


def _update_database(conn: Connection, current: DatabaseVersion) -> DatabaseVersion:
    next_version, update_operation = _check_for_database_updates(current)
    logger.info(f"Attempting local database upgrade from version {current} to {next_version}")
    _apply_database_update(conn, next_version, update_operation)
    logger.info("Update successful.")
    return next_version


def _check_for_database_updates(current: DatabaseVersion) -> tuple[DatabaseVersion, UpdateOperation]:
    if current.next_patch() in __UPDATE_PATH__:
        next_version = current.next_patch()
    elif current.next_minor() in __UPDATE_PATH__:
        next_version = current.next_minor()
    elif current.next_major() in __UPDATE_PATH__:
        next_version = current.next_major()
    else:
        raise NotImplementedError(
            f"Unable to find a update path to version {__REQUIRED_DATABASE_VERSION__}. "
            f"Stuck at {current}."
        )
    return next_version, __UPDATE_PATH__[next_version]


def _apply_database_update(conn: Connection, next_version: DatabaseVersion, update: UpdateOperation):
    try:
        with conn:
            c = conn.cursor()
            update(c)
            set_version_setting(c, next_version)
    except Exception as err:
        logger.exception(
            "Error during update. Changes are automatically rolled back to previous successful update. "
            f"Quiting with the following error: {err}"
        )
        raise err


def get_version_setting(cursor: Cursor) -> str:
    cursor.execute(
        query="""
            SELECT value FROM settings WHERE parameter = '_version'
        """
    )
    return cursor.fetchone()


def set_version_setting(cursor: Cursor, version: DatabaseVersion):
    cursor.execute(
        """
            INSERT OR REPLACE INTO
                settings (parameter, value)
            VALUES
                ('_version', ?)
        """,
        (version.__repr__(), ),
    )
