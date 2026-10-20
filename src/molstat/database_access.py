"""Narrow Windows file repair and a non-destructive writer directory check."""
from __future__ import annotations

import errno
import os
from pathlib import Path
import sqlite3
import stat
import tempfile


_IS_WINDOWS = os.name == "nt"
_SIDECARS = ("-journal", "-wal", "-shm")


class DatabaseAccessError(sqlite3.OperationalError):
    """Safe diagnostics for filesystem failures before opening SQLite."""

    def __init__(self, stage: str, cause: OSError) -> None:
        directory = stage == "database_directory"
        self.database_stage = stage
        winerror = getattr(cause, "winerror", None)
        if cause.errno == errno.ENOSPC or winerror == 112:
            name = "SQLITE_FULL"
        elif cause.errno in (errno.EACCES, errno.EPERM) or winerror in (5, 19, 65):
            name = "SQLITE_READONLY_DIRECTORY" if directory else "SQLITE_READONLY"
        elif cause.errno == errno.EIO:
            name = "SQLITE_IOERR"
        else:
            # Missing/invalid paths and rejected sidecar links are open failures,
            # not evidence of a write-protected file or directory.
            name = "SQLITE_CANTOPEN"
        self.sqlite_errorname = name
        self.sqlite_errorcode = getattr(sqlite3, name)
        value = winerror
        if not isinstance(value, int):
            value = cause.errno
        self.os_errorcode = value if isinstance(value, int) else None
        # Never copy an OS exception's message: it can include a private path.
        super().__init__(self.sqlite_errorname)


def prepare_writer_files(path: Path) -> None:
    """Clear only Windows' read-only flag on this database and its sidecars.

    SQLite can silently open a write-protected file read-only. Repair the known
    flag before creating a writer connection, without changing ACLs, directory
    permissions, or journal contents. Reader connections must not call this.
    """
    if not _IS_WINDOWS:
        return
    candidates = (path, *(path.with_name(path.name + suffix) for suffix in _SIDECARS))
    for index, candidate in enumerate(candidates):
        try:
            try:
                details = candidate.lstat()
            except FileNotFoundError:
                continue
            if index and (
                stat.S_ISLNK(details.st_mode)
                or getattr(details, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise OSError(errno.ELOOP, "SQLite sidecar must not be a link.")
            if index == 0 and stat.S_ISLNK(details.st_mode):
                # The explicitly selected database may itself be a symlink;
                # inspect its target rather than repairing the link's flags.
                details = candidate.stat()
            if not stat.S_ISREG(details.st_mode):
                raise OSError(errno.EINVAL, "SQLite file must be a regular file.")
            if getattr(details, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_READONLY:
                # On Windows chmod changes only FILE_ATTRIBUTE_READONLY. It
                # does not reset other attributes or edit the security ACL.
                candidate.chmod(stat.S_IWRITE)
        except OSError as exc:
            raise DatabaseAccessError("database_access", exc) from exc


def probe_writer_directory(path: Path) -> None:
    """Check create/write/fsync/rename/delete using only our temporary file.

    This complements the real SQLite lease transaction: a writable database
    alone is insufficient when its parent cannot create a rollback journal.
    """
    owned: Path | None = None
    failure: OSError | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".molstat-write-probe-", dir=path.parent)
        owned = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(b"MolStat synthetic directory access check\n")
            stream.flush()
            os.fsync(stream.fileno())
        renamed = owned.with_name(owned.name + ".moved")
        owned.rename(renamed)
        owned = renamed
        owned.unlink()
        owned = None
    except OSError as exc:
        failure = exc
    finally:
        if owned is not None:
            try:
                owned.unlink(missing_ok=True)
            except OSError as exc:
                # Preserve the first failure if cleanup is denied as well.
                if failure is None:
                    failure = exc
    if failure is not None:
        raise DatabaseAccessError("database_directory", failure) from failure
