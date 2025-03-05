import logging
from typing import Callable, Tuple, Dict

from core_tools.data.SQL.model.versions.v1_0_0 import initialise_v1_0_0
from core_tools.data.SQL.model.versions.v1_1_0 import update_to_v1_1_0

from psycopg2._psycopg import connection as Connection, cursor as Cursor, Error as PGError
from psycopg2.extras import RealDictCursor


logger = logging.getLogger(__name__)


UpdateOperation = Callable[[Cursor], None]


class DatabaseVersion:
    def __init__(self, major: int, minor: int, patch: int):
        self.major = major
        self.minor = minor
        self.patch = patch

    def next_patch(self):
        return DatabaseVersion(self.major, self.minor, self.patch + 1)

    def next_minor(self):
        return DatabaseVersion(self.major, self.minor + 1, 0)

    def next_major(self):
        return DatabaseVersion(self.major + 1, 0, 0)

    def __eq__(self, other):
        return (self.major == other.major) and (self.minor == other.minor) and (self.patch == other.patch)

    def __lt__(self, other):
        return (self.major < other.major) or (self.major == other.major and self.minor < other.minor) or (self.major == other.major and self.minor == other.minor and self.patch < other.patch)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __gt__(self, other):
        return not (self.__eq__(other) or self.__lt__(other))

    def __le__(self, other):
        return self.__eq__(other) or self.__lt__(other)

    def __ge__(self, other):
        return not self.__lt__(other)

    def __repr__(self) -> str:
        return "{}.{}.{}".format(self.major, self.minor, self.patch)

    def __hash__(self):
        return hash((self.major, self.minor, self.patch))


__REQUIRED_DATABASE_VERSION__ = DatabaseVersion(1, 1, 0)

__UPDATE_PATH__: Dict[DatabaseVersion, UpdateOperation] = {
    DatabaseVersion(1, 1, 0): update_to_v1_1_0,
}


def local_database_update_routine(conn: Connection):
    version = get_database_version(conn)

    if version.major == 0:
        with conn:
            cursor = conn.cursor()
            initialise_v1_0_0(cursor)
        version = DatabaseVersion(1, 0, 0)

    if version < __REQUIRED_DATABASE_VERSION__:
        logger.warning(
            "Expected local database version {}, but found {}. Performing updates. This can take a while, depeninding on the setup.".format(__REQUIRED_DATABASE_VERSION__, version)
        )

    while version < __REQUIRED_DATABASE_VERSION__:
        version = _update_database(conn, version)


def get_database_version(conn: Connection) -> DatabaseVersion:
    try:
        with conn:
            c = conn.cursor(cursor_factory=RealDictCursor)
            c.execute(
                query="SELECT major, minor, patch FROM database_version",
            )
            records = c.fetchall()
        assert len(records) == 1, "Either no or more than one entries in database_version table"
        record = records[0]
        return DatabaseVersion(major=record["major"], minor=record["minor"], patch=record["patch"])
    except PGError as err:
        if err.pgcode == "42P01":
            # 42P01 is the psycopg2 error code for UndefinedTable
            logger.debug("No table 'database_version' found, returning v0.0.0")
            return DatabaseVersion(0, 0, 0)
        raise err


def _update_database(conn: Connection, current: DatabaseVersion) -> DatabaseVersion:
    next_version, update_operation = _check_for_database_updates(current)
    logger.info("Attempting local database upgrade from version {} to {}".format(current, next_version))
    _apply_database_update(conn, update_operation)
    logger.info("Update successful.")
    return next_version


def _check_for_database_updates(current: DatabaseVersion) -> Tuple[DatabaseVersion, UpdateOperation]:
    if current.next_patch() in __UPDATE_PATH__:
        next_version = current.next_patch()
    elif current.next_minor() in __UPDATE_PATH__:
        next_version = current.next_minor()
    elif current.next_major() in __UPDATE_PATH__:
        next_version = current.next_major()
    else:
        raise NotImplementedError("Unable to find a update path to version {}. Stuck at {}.".format(__REQUIRED_DATABASE_VERSION__, current))
    return next_version, __UPDATE_PATH__[next_version]


def _apply_database_update(conn: Connection, update: UpdateOperation):
    try:
        with conn:
            c = conn.cursor()
            update(c)
    except Exception as err:
        logger.exception(
            "Error during update. Changes are automatically rolled back to previous successful update. Quiting with the following error: {}".format(err)
        )
        raise err
