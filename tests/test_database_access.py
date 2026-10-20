"""Writer access repairs use synthetic files and never discard SQLite journals."""

from contextlib import closing
import ctypes
import errno
import importlib
import os
from pathlib import Path
import sqlite3
import stat
from types import SimpleNamespace

import pytest


def access_module():
    return importlib.import_module("molstat.database_access")


@pytest.mark.parametrize("stage", ["database_access", "database_directory"])
@pytest.mark.parametrize(
    "os_errno,winerror,expected",
    [
        (errno.ENOSPC, None, "SQLITE_FULL"),
        (errno.EACCES, 112, "SQLITE_FULL"),
        (errno.EIO, None, "SQLITE_IOERR"),
        (errno.EACCES, None, "SQLITE_READONLY"),
        (errno.EPERM, None, "SQLITE_READONLY"),
        (errno.EIO, 5, "SQLITE_READONLY"),
        (errno.EIO, 19, "SQLITE_READONLY"),
        (errno.EIO, 65, "SQLITE_READONLY"),
        (errno.ENOENT, None, "SQLITE_CANTOPEN"),
        (errno.ENOTDIR, None, "SQLITE_CANTOPEN"),
        (errno.EINVAL, None, "SQLITE_CANTOPEN"),
        (errno.ELOOP, None, "SQLITE_CANTOPEN"),
    ],
)
def test_os_failures_keep_their_actual_sqlite_category(stage, os_errno, winerror, expected):
    access = access_module()
    cause = OSError(os_errno, "PRIVATE-PATH-PAYLOAD")
    if winerror is not None:
        cause.winerror = winerror
    if expected == "SQLITE_READONLY" and stage == "database_directory":
        expected = "SQLITE_READONLY_DIRECTORY"

    failure = access.DatabaseAccessError(stage, cause)

    assert failure.sqlite_errorname == expected
    assert failure.sqlite_errorcode == getattr(sqlite3, expected)
    assert failure.database_stage == stage
    assert failure.os_errorcode == (winerror if winerror is not None else os_errno)
    assert "PRIVATE" not in str(failure)


@pytest.mark.skipif(os.name != "nt", reason="Windows file attributes")
@pytest.mark.parametrize("suffix", ["", "-journal", "-wal", "-shm"])
def test_prepare_writer_clears_only_readonly_on_known_files(tmp_path, suffix):
    access = access_module()
    database = tmp_path / "synthetic.sqlite3"
    protected = database.with_name(database.name + suffix)
    protected.write_bytes(b"PRESERVE-SYNTHETIC-CONTENTS")
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_bytes(b"UNRELATED")
    unrelated.chmod(stat.S_IREAD)
    protected.chmod(stat.S_IREAD)
    try:
        access.prepare_writer_files(database)

        assert protected.read_bytes() == b"PRESERVE-SYNTHETIC-CONTENTS"
        assert not protected.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
        assert unrelated.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
        assert unrelated.read_bytes() == b"UNRELATED"
        assert set(tmp_path.iterdir()) == {protected, unrelated}
    finally:
        protected.chmod(stat.S_IWRITE)
        unrelated.chmod(stat.S_IWRITE)


@pytest.mark.skipif(os.name != "nt", reason="Windows SQLite opening fallback")
def test_repaired_real_database_can_write_without_losing_existing_rows(tmp_path):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE synthetic(value TEXT)")
        connection.execute("INSERT INTO synthetic VALUES ('PRESERVED')")
        connection.commit()
    path.chmod(stat.S_IREAD)
    try:
        with closing(sqlite3.connect(path)) as connection:
            with pytest.raises(sqlite3.OperationalError) as readonly:
                connection.execute("INSERT INTO synthetic VALUES ('REJECTED')")
            assert readonly.value.sqlite_errorcode == sqlite3.SQLITE_READONLY

        access.prepare_writer_files(path)

        with closing(sqlite3.connect(path)) as connection:
            connection.execute("INSERT INTO synthetic VALUES ('NEW')")
            connection.commit()
            assert connection.execute("SELECT value FROM synthetic").fetchall() == [
                ("PRESERVED",), ("NEW",)
            ]
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        path.chmod(stat.S_IWRITE)


@pytest.mark.skipif(os.name != "nt", reason="Windows SQLite journal attributes")
def test_readonly_journal_is_preserved_then_sqlite_can_reuse_it(tmp_path):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE synthetic(value TEXT)")
        connection.execute("INSERT INTO synthetic VALUES ('PRESERVED')")
        connection.commit()
    journal = path.with_name(path.name + "-journal")
    journal.write_bytes(b"")
    journal.chmod(stat.S_IREAD)
    try:
        with closing(sqlite3.connect(path)) as connection:
            with pytest.raises(sqlite3.OperationalError) as readonly:
                connection.execute("INSERT INTO synthetic VALUES ('REJECTED')")
                connection.commit()
            assert readonly.value.sqlite_errorcode & 0xFF == sqlite3.SQLITE_IOERR

        access.prepare_writer_files(path)

        assert journal.is_file()
        assert journal.read_bytes() == b""
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("INSERT INTO synthetic VALUES ('NEW')")
            connection.commit()
            assert connection.execute("SELECT value FROM synthetic").fetchall() == [
                ("PRESERVED",), ("NEW",)
            ]
    finally:
        if journal.exists():
            journal.chmod(stat.S_IWRITE)


@pytest.mark.skipif(os.name != "nt", reason="Windows file attributes")
def test_prepare_preserves_hidden_attribute(tmp_path):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    path.write_bytes(b"PRESERVED")
    set_attributes = ctypes.windll.kernel32.SetFileAttributesW
    set_attributes.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    set_attributes.restype = ctypes.c_int
    assert set_attributes(str(path), stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_READONLY)
    try:
        access.prepare_writer_files(path)

        assert path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN
        assert not path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
    finally:
        assert set_attributes(str(path), stat.FILE_ATTRIBUTE_NORMAL)


def test_prepare_does_nothing_on_non_windows(tmp_path, monkeypatch):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    path.write_bytes(b"PRESERVED")
    calls = []
    monkeypatch.setattr(access, "_IS_WINDOWS", False)
    monkeypatch.setattr(Path, "chmod", lambda *args: calls.append(args))

    access.prepare_writer_files(path)

    assert not calls
    assert path.read_bytes() == b"PRESERVED"


def test_prepare_missing_database_and_sidecars_does_not_create_files(tmp_path):
    access = access_module()

    access.prepare_writer_files(tmp_path / "synthetic.sqlite3")

    assert list(tmp_path.iterdir()) == []


def test_denied_readonly_repair_retains_safe_error_and_cause(tmp_path, monkeypatch):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    path.write_bytes(b"PRESERVED")
    original_stat = Path.stat
    monkeypatch.setattr(access, "_IS_WINDOWS", True)

    def file_stat(candidate, *args, **kwargs):
        value = original_stat(candidate, *args, **kwargs)
        return SimpleNamespace(st_mode=value.st_mode,
                               st_file_attributes=stat.FILE_ATTRIBUTE_READONLY)

    denied = PermissionError(errno.EACCES, "PRIVATE-PATH-PAYLOAD")
    denied.winerror = 5
    monkeypatch.setattr(Path, "stat", file_stat)
    monkeypatch.setattr(Path, "chmod", lambda *args: (_ for _ in ()).throw(denied))

    with pytest.raises(access.DatabaseAccessError) as failure:
        access.prepare_writer_files(path)

    assert failure.value.__cause__ is denied
    assert failure.value.sqlite_errorcode == sqlite3.SQLITE_READONLY
    assert failure.value.sqlite_errorname == "SQLITE_READONLY"
    assert failure.value.database_stage == "database_access"
    assert failure.value.os_errorcode == 5
    assert "PRIVATE" not in str(failure.value)
    assert path.read_bytes() == b"PRESERVED"


def test_sidecar_link_is_rejected_without_touching_its_target(tmp_path, monkeypatch):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"EXTERNAL-PRESERVED")
    sidecar = path.with_name(path.name + "-journal")
    sidecar.write_bytes(b"LINK-PLACEHOLDER")
    original_lstat = Path.lstat
    monkeypatch.setattr(access, "_IS_WINDOWS", True)

    def linked_stat(candidate):
        if candidate == sidecar:
            return SimpleNamespace(st_mode=stat.S_IFLNK,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return original_lstat(candidate)

    chmod_calls = []
    monkeypatch.setattr(Path, "lstat", linked_stat)
    monkeypatch.setattr(Path, "chmod", lambda *args: chmod_calls.append(args))

    with pytest.raises(access.DatabaseAccessError) as failure:
        access.prepare_writer_files(path)

    assert failure.value.database_stage == "database_access"
    assert not chmod_calls
    assert outside.read_bytes() == b"EXTERNAL-PRESERVED"
    assert sidecar.read_bytes() == b"LINK-PLACEHOLDER"


@pytest.mark.parametrize("suffix", ["", "-journal"])
def test_directory_at_database_or_sidecar_path_is_never_changed(tmp_path, monkeypatch, suffix):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    directory = path.with_name(path.name + suffix)
    directory.mkdir()
    preserved = directory / "preserved.json"
    preserved.write_bytes(b"PRESERVED")
    monkeypatch.setattr(access, "_IS_WINDOWS", True)
    chmod_calls = []
    monkeypatch.setattr(Path, "chmod", lambda *args: chmod_calls.append(args))

    with pytest.raises(access.DatabaseAccessError) as failure:
        access.prepare_writer_files(path)

    assert failure.value.os_errorcode == errno.EINVAL
    assert not chmod_calls
    assert preserved.read_bytes() == b"PRESERVED"


def test_denied_file_inspection_is_not_mistaken_for_missing_file(tmp_path, monkeypatch):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    denied = PermissionError(errno.EACCES, "PRIVATE-PATH-PAYLOAD")
    monkeypatch.setattr(access, "_IS_WINDOWS", True)
    monkeypatch.setattr(Path, "lstat", lambda *args: (_ for _ in ()).throw(denied))

    with pytest.raises(access.DatabaseAccessError) as failure:
        access.prepare_writer_files(path)

    assert failure.value.__cause__ is denied
    assert failure.value.database_stage == "database_access"
    assert failure.value.os_errorcode == errno.EACCES
    assert "PRIVATE" not in str(failure.value)


def test_directory_probe_leaves_database_and_sidecars_untouched(tmp_path):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    contents = {path: b"DATABASE", path.with_name(path.name + "-journal"): b"JOURNAL",
                tmp_path / ".molstat-write-probe-unrelated": b"UNRELATED"}
    for candidate, data in contents.items():
        candidate.write_bytes(data)

    access.probe_writer_directory(path)

    assert set(tmp_path.iterdir()) == set(contents)
    assert all(candidate.read_bytes() == data for candidate, data in contents.items())


@pytest.mark.parametrize("operation", ["fsync", "rename", "unlink"])
def test_failed_probe_cleans_only_own_files_and_preserves_cause(tmp_path, monkeypatch, operation):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    path.write_bytes(b"DATABASE")
    unrelated = tmp_path / ".molstat-write-probe-unrelated"
    unrelated.write_bytes(b"UNRELATED")
    denied = PermissionError(errno.EACCES, "PRIVATE-PATH-PAYLOAD")
    if operation == "fsync":
        monkeypatch.setattr(access.os, "fsync", lambda *args: (_ for _ in ()).throw(denied))
    else:
        original = getattr(Path, operation)
        calls = 0

        def denied_once(candidate, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise denied
            return original(candidate, *args, **kwargs)

        monkeypatch.setattr(Path, operation, denied_once)

    with pytest.raises(access.DatabaseAccessError) as failure:
        access.probe_writer_directory(path)

    assert failure.value.__cause__ is denied
    assert failure.value.database_stage == "database_directory"
    assert failure.value.sqlite_errorname == "SQLITE_READONLY_DIRECTORY"
    assert failure.value.os_errorcode == errno.EACCES
    assert "PRIVATE" not in str(failure.value)
    assert set(tmp_path.iterdir()) == {path, unrelated}
    assert path.read_bytes() == b"DATABASE"
    assert unrelated.read_bytes() == b"UNRELATED"


def test_missing_probe_parent_returns_safe_os_failure(tmp_path):
    access = access_module()

    with pytest.raises(access.DatabaseAccessError) as failure:
        access.probe_writer_directory(tmp_path / "missing" / "synthetic.sqlite3")

    assert failure.value.database_stage == "database_directory"
    assert failure.value.os_errorcode is not None
    assert isinstance(failure.value.__cause__, OSError)
    assert not (tmp_path / "missing").exists()


def test_denied_probe_cleanup_never_masks_first_failure(tmp_path, monkeypatch):
    access = access_module()
    path = tmp_path / "synthetic.sqlite3"
    unrelated = tmp_path / ".molstat-write-probe-unrelated"
    unrelated.write_bytes(b"PRESERVED")
    first_failure = PermissionError(errno.EACCES, "PRIVATE-FIRST-FAILURE")
    cleanup_failure = OSError(errno.EIO, "PRIVATE-CLEANUP-FAILURE")
    monkeypatch.setattr(access.os, "fsync", lambda *args: (_ for _ in ()).throw(first_failure))
    monkeypatch.setattr(Path, "unlink", lambda *args, **kwargs: (_ for _ in ()).throw(cleanup_failure))

    with pytest.raises(access.DatabaseAccessError) as failure:
        access.probe_writer_directory(path)

    assert failure.value.__cause__ is first_failure
    assert failure.value.os_errorcode == errno.EACCES
    assert "PRIVATE" not in str(failure.value)
    assert unrelated.read_bytes() == b"PRESERVED"
