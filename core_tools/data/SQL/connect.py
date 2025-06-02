"""
definition of storage locations and initializer for storage.
"""

from core_tools.data.name_validation import validate_data_identifier_value


class sample_info:
    project: str | None = None
    set_up: str | None = None
    sample: str | None = None
    scope: str | None = None

    def __init__(self, project, set_up, sample, scope):
        if project is not None:
            validate_data_identifier_value(project)
        if set_up is not None:
            validate_data_identifier_value(set_up)
        if sample is not None:
            validate_data_identifier_value(sample)
        if scope is not None:
            validate_data_identifier_value(scope)

        sample_info.project = project
        sample_info.set_up = set_up
        sample_info.sample = sample
        sample_info.scope = scope

    def __str__(self) -> str:
        return f"{sample_info.project}: {sample_info.set_up}-{sample_info.sample}"


class SQL_conn_info_local:
    host: str | None = None
    port: int = None
    user: str | None = None
    passwd: str | None = None
    dbname: str | None = None
    readonly: bool = False

    def __init__(self, host, port, user, passwd, dbname, readonly=False):
        SQL_conn_info_local.host = host
        SQL_conn_info_local.port = port
        SQL_conn_info_local.user = user
        SQL_conn_info_local.passwd = passwd
        SQL_conn_info_local.dbname = dbname
        SQL_conn_info_local.readonly = readonly

    def __repr__(self):
        return (
            f'{self.__class__}: host {self.host}, port {self.port}, user {self.user}, passwd *, '
            f'dbname {self.dbname}, readonly {self.readonly}'
        )


class SQL_conn_info_remote:
    host: str | None = None
    port: int = None
    user: str | None = None
    passwd: str | None = None
    dbname: str | None = None
    readonly: bool = False

    def __init__(self, host, port, user, passwd, dbname, readonly=False):
        SQL_conn_info_remote.host = host
        SQL_conn_info_remote.port = port
        SQL_conn_info_remote.user = user
        SQL_conn_info_remote.passwd = passwd
        SQL_conn_info_remote.dbname = dbname
        SQL_conn_info_remote.readonly = readonly

    def __repr__(self):
        return (
            f'{self.__class__}: host {self.host}, port {self.port}, user {self.user}, passwd *, '
            f'dbname {self.dbname}, readonly {self.readonly}'
        )


def set_up_local_storage(
        user,
        passwd,
        dbname,
        project,
        set_up,
        sample,
        scope=None,
        readonly=False
):
    """
    Set up the specification for the datastorage needed to store/retrieve measurements.

    Args:
        user (str) : name of the user to connect with
        passwd (str) : password of the user
        dbname (str) : database to connect with (e.g. 'vandersypen_data')

        project (str) : project for which the data will be saved
        set_up (str) : set up at which the data has been measured
        sample (str) : sample name
        scope (str|None) : SQDL scope name, can be None for setups that do not use SQDL.
    """
    SQL_conn_info_local('localhost', 5432, user, passwd, dbname, readonly)
    sample_info(project, set_up, sample, scope)


def set_up_remote_storage(
    host,
    port,
    user,
    passwd,
    dbname,
    project,
    set_up,
    sample,
    scope=None,
    readonly=False
):
    """
    Set up the specification for the datastorage needed to store/retrieve measurements.

    Args:
        host (str) : host that is used for storage, e.g. "vanvliet.qutech.tudelft.nl"
        port (int) : port number to connect through, the default it 5432
        user (str) : name of the user to connect with
        passwd (str) : password of the user
        dbname (str) : database to connect with (e.g. 'vandersypen_data')

        project (str) : project for which the data will be saved
        set_up (str) : set up at which the data has been measured
        sample (str) : sample name
        scope (str|None) : SQDL scope name, can be None for setups that do not use SQDL.
    """
    SQL_conn_info_remote(host, port, user, passwd, dbname, readonly)
    sample_info(project, set_up, sample, scope)


def set_up_local_and_remote_storage(
    host,
    port,
    user_local,
    passwd_local,
    dbname_local,
    user_remote,
    passwd_remote,
    dbname_remote,
    project,
    set_up,
    sample,
    scope=None,
    local_readonly=False,
    remote_readonly=False
):
    """
    Set up the specification for the datastorage needed to store/retrieve measurements.

    Args:
        host (str) : host that is used for storage, e.g. "vanvliet.qutech.tudelft.nl"
        port (int) : port number to connect through, the default it 5432

        user_local (str) : [local server] name of the user to connect with
        passwd_local (str) : [local server] password of the user
        dbname_local (str) : [local server] database to connect with (e.g. 'vandersypen_data')

        user_remote (str) : [remote server] name of the user to connect with
        passwd_remote (str) : [remote server] password of the user
        dbname_remote (str) : [remote server] database to connect with (e.g. 'vandersypen_data')

        project (str) : project for which the data will be saved
        set_up (str) : set up at which the data has been measured
        sample (str) : sample name
        scope (str|None) : SQDL scope name, can be None for setups that do not use SQDL.
    """
    SQL_conn_info_local('localhost', 5432, user_local, passwd_local, dbname_local, local_readonly)
    SQL_conn_info_remote(host, port, user_remote, passwd_remote, dbname_remote, remote_readonly)
    sample_info(project, set_up, sample, scope)
