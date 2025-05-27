import os
from contextlib import contextmanager


@contextmanager
def atomic_write(fname: str):
    """
    Atomic write of a file avoiding partially written files.
    Returns the file name with suffix '.tmp'.
    After writing renames the tmp file, replacing any
    existing file.
    When an old file is replaced there can be a
    short moment that there is no file.
    """
    tmp_file = f"{fname}.tmp"
    if os.path.exists(tmp_file):
        os.remove(tmp_file)

    yield tmp_file

    try:
        os.rename(tmp_file, fname)
    except FileExistsError:
        os.remove(fname)
        os.rename(tmp_file, fname)
