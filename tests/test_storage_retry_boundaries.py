"""Retry only preflight and individual file operations, never committed imports."""
from contextlib import closing
from datetime import timedelta
import errno
import os
from pathlib import Path
import sqlite3
import stat
from threading import Event

import pytest

from molstat.database import ManagedConnection, MolStatDatabase, readonly_uri
from molstat.excel_search import publish_search_workbook, read_excel_snapshot
from molstat.private_delivery import install_private_files
from molstat.publisher import PublicationPolicy, SharePointPublisher


def fast_retries(monkeypatch):
    from molstat import recovery
    pauses = []
    monkeypatch.setattr(recovery, "_sleep", pauses.append)
    return pauses


def database(tmp_path):
    value = MolStatDatabase(tmp_path / "synthetic.sqlite3")
    value.migrate()
    return value


def test_writer_probe_reopens_a_silently_readonly_connection_before_return(tmp_path, monkeypatch):
    pauses = fast_retries(monkeypatch)
    db = database(tmp_path)
    original = sqlite3.connect
    opened = []

    def readonly_once(path, *args, **kwargs):
        if not opened:
            result = original(readonly_uri(db.path), uri=True, isolation_level=None,
                              factory=ManagedConnection)
        else:
            result = original(path, *args, **kwargs)
        opened.append(result)
        return result

    monkeypatch.setattr(sqlite3, "connect", readonly_once)

    with db._connect() as connection:
        connection.execute("INSERT INTO sample(molstat_key,first_seen_at,last_seen_at) VALUES ('SYNTHETIC','now','now')")

    assert len(opened) == 2
    assert len(pauses) == 1
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    with db.read_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone() == (1,)


def test_writer_probe_preserves_bytes_and_user_version(tmp_path, monkeypatch):
    fast_retries(monkeypatch)
    db = database(tmp_path)
    with closing(sqlite3.connect(db.path)) as connection:
        connection.execute("PRAGMA user_version = 317")
    before = db.path.read_bytes()

    with db._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (317,)
        assert not connection.in_transaction

    assert db.path.read_bytes() == before


def test_persistently_readonly_preflight_closes_every_attempt(tmp_path, monkeypatch):
    pauses = fast_retries(monkeypatch)
    db = database(tmp_path)
    original = sqlite3.connect
    opened = []

    def readonly(path, *args, **kwargs):
        result = original(readonly_uri(db.path), uri=True, isolation_level=None,
                          factory=ManagedConnection)
        opened.append(result)
        return result

    monkeypatch.setattr(sqlite3, "connect", readonly)

    with pytest.raises(sqlite3.OperationalError) as failure:
        db._connect()

    assert failure.value.sqlite_errorcode == sqlite3.SQLITE_READONLY
    assert len(opened) == 5
    assert pauses == [5.0, 15.0, 30.0, 60.0]
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


@pytest.mark.parametrize("code", [sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_FULL, sqlite3.SQLITE_IOERR])
def test_preflight_does_not_retry_corrupt_full_or_ambiguous_io_errors(tmp_path, monkeypatch, code):
    pauses = fast_retries(monkeypatch)
    db = database(tmp_path)
    calls = []

    def rejected(*args, **kwargs):
        calls.append(1)
        failure = sqlite3.OperationalError("PRIVATE-ERROR")
        failure.sqlite_errorcode = code
        failure.sqlite_errorname = {sqlite3.SQLITE_CORRUPT: "SQLITE_CORRUPT",
                                   sqlite3.SQLITE_FULL: "SQLITE_FULL",
                                   sqlite3.SQLITE_IOERR: "SQLITE_IOERR"}[code]
        raise failure

    monkeypatch.setattr(sqlite3, "connect", rejected)
    with pytest.raises(sqlite3.OperationalError):
        db._connect()

    assert calls == [1]
    assert pauses == []


def test_business_commit_failure_is_never_retried(tmp_path, monkeypatch):
    pauses = fast_retries(monkeypatch)
    db = database(tmp_path)
    commits = []

    class CommitFailure(ManagedConnection):
        def execute(self, sql, parameters=()):
            if sql == "COMMIT":
                commits.append(sql)
                failure = sqlite3.OperationalError("PRIVATE-COMMIT-ERROR")
                failure.sqlite_errorcode = sqlite3.SQLITE_IOERR
                failure.sqlite_errorname = "SQLITE_IOERR"
                raise failure
            return super().execute(sql, parameters)

    original = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs:
                        original(*args, **{**kwargs, "factory": CommitFailure}))

    with pytest.raises(sqlite3.OperationalError):
        with db._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO sample(molstat_key,first_seen_at,last_seen_at) VALUES ('SYNTHETIC','now','now')")
            connection.execute("COMMIT")

    assert commits == ["COMMIT"]
    assert pauses == []
    with db.read_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone() == (0,)


def test_writer_probe_does_not_mutate_after_lease_token_changed(tmp_path, monkeypatch):
    from molstat._writer_lease import WriterLeaseLost
    pauses = fast_retries(monkeypatch)
    db = database(tmp_path)
    with db.writer_lease("synthetic", timedelta(minutes=5), renew=True):
        with db._connect(guard_lease=False) as connection:
            connection.execute("UPDATE writer_lease SET token='successor'")
        before = db.path.read_bytes()
        with pytest.raises(WriterLeaseLost):
            db._connect()
        assert db.path.read_bytes() == before
    assert pauses == []


def test_excel_retries_same_validated_candidate_without_regenerating(tmp_path, monkeypatch):
    from datetime import datetime
    pauses = fast_retries(monkeypatch)
    snapshot = read_excel_snapshot(database(tmp_path), generated_at=datetime(2026, 10, 20))
    target = tmp_path / "Prøvesøk.xlsx"
    candidates = []

    def locked_once(source, destination):
        candidates.append(Path(source))
        if len(candidates) == 1:
            raise PermissionError(errno.EACCES, "PRIVATE-LOCK")
        os.replace(source, destination)

    result = publish_search_workbook(snapshot, target, replace=locked_once)

    assert result.status == "published"
    assert candidates[0] == candidates[1]
    assert len(pauses) == 1
    assert target.is_file()


@pytest.mark.parametrize("error_kind", ["access", "io", "cancel"])
def test_excel_completed_replace_is_verified_instead_of_retried(tmp_path, monkeypatch, error_kind):
    from datetime import datetime
    from molstat.recovery import recovery_context
    pauses = fast_retries(monkeypatch)
    snapshot = read_excel_snapshot(database(tmp_path), generated_at=datetime(2026, 10, 20))
    target = tmp_path / "Prøvesøk.xlsx"
    target.write_bytes(b"PREVIOUS")
    calls = []
    cancel = Event()

    def completed_then_failed(source, destination):
        calls.append(1)
        os.replace(source, destination)
        if error_kind == "cancel":
            cancel.set()
        if error_kind == "io":
            raise OSError(errno.EIO, "PRIVATE-ALREADY-MOVED")
        raise PermissionError(errno.EACCES, "PRIVATE-ALREADY-MOVED")

    with recovery_context(cancel=cancel):
        result = publish_search_workbook(snapshot, target, replace=completed_then_failed)

    assert result.status == "published"
    assert calls == [1]
    assert pauses == []
    assert target.read_bytes().startswith(b"PK")


def test_excel_uncertain_io_keeps_validated_candidate_and_previous_workbook(tmp_path, monkeypatch):
    from datetime import datetime
    from molstat.excel_search import validate_search_workbook
    pauses = fast_retries(monkeypatch)
    snapshot = read_excel_snapshot(database(tmp_path), generated_at=datetime(2026, 10, 20))
    target = tmp_path / "Prøvesøk.xlsx"
    target.write_bytes(b"PREVIOUS")

    def uncertain(source, destination):
        raise OSError(errno.EIO, "PRIVATE-UNCERTAIN")

    with pytest.raises(OSError):
        publish_search_workbook(snapshot, target, replace=uncertain)

    pending = list(tmp_path.glob(".Prøvesøk.*.pending.xlsx"))
    assert len(pending) == 1
    assert validate_search_workbook(pending[0]) is None
    assert target.read_bytes() == b"PREVIOUS"
    assert pauses == []


def test_excel_cancellation_while_locked_keeps_validated_candidate(tmp_path, monkeypatch):
    from datetime import datetime
    from molstat.failures import RunFailure
    from molstat.recovery import recovery_context
    fast_retries(monkeypatch)
    snapshot = read_excel_snapshot(database(tmp_path), generated_at=datetime(2026, 10, 20))
    target = tmp_path / "Prøvesøk.xlsx"
    target.write_bytes(b"PREVIOUS")
    cancel = Event()

    def locked(source, destination):
        cancel.set()
        raise PermissionError(errno.EACCES, "PRIVATE-LOCK")

    with recovery_context(cancel=cancel), pytest.raises(RunFailure) as failure:
        publish_search_workbook(snapshot, target, replace=locked)

    assert failure.value.code == "CANCELLED"
    assert len(list(tmp_path.glob(".Prøvesøk.*.pending.xlsx"))) == 1
    assert target.read_bytes() == b"PREVIOUS"


def test_excel_consumed_candidate_with_wrong_target_bytes_is_never_reported_as_locked(tmp_path, monkeypatch):
    from datetime import datetime
    pauses = fast_retries(monkeypatch)
    snapshot = read_excel_snapshot(database(tmp_path), generated_at=datetime(2026, 10, 20))
    target = tmp_path / "Prøvesøk.xlsx"

    def corrupted_after_replace(source, destination):
        os.replace(source, destination)
        Path(destination).write_bytes(b"UNVERIFIED-TARGET")
        raise PermissionError(errno.EACCES, "PRIVATE-UNCERTAIN")

    with pytest.raises(PermissionError):
        publish_search_workbook(snapshot, target, replace=corrupted_after_replace)

    assert pauses == []


def public_files(tmp_path):
    sources = {}
    target = tmp_path / "public"
    target.mkdir()
    for name in ("antall.csv", "resultater.csv"):
        sources[name] = tmp_path / name
        sources[name].write_text("Analyse\nSYNTHETIC\n", encoding="utf-8")
        (target / name).write_bytes(b"OLD-" + name.encode())
    publisher = SharePointPublisher(PublicationPolicy(
        {name: frozenset({"Analyse"}) for name in sources}, (),
    ))
    return publisher, sources, target


def test_public_install_retries_transient_replace_without_reprocessing(tmp_path, monkeypatch):
    pauses = fast_retries(monkeypatch)
    publisher, files, target = public_files(tmp_path)
    original = os.replace
    failed = []

    def denied_once(source, destination):
        if Path(destination) == target / "resultater.csv" and not failed:
            failed.append(Path(source))
            raise PermissionError(errno.EACCES, "PRIVATE-LOCK")
        return original(source, destination)

    monkeypatch.setattr(os, "replace", denied_once)

    publisher.publish(files, target)

    assert len(pauses) == 1
    assert all((target / name).read_bytes() == source.read_bytes() for name, source in files.items())


@pytest.mark.skipif(os.name != "nt", reason="Windows readonly propagation")
def test_public_delivery_never_copies_source_readonly_attributes(tmp_path, monkeypatch):
    fast_retries(monkeypatch)
    publisher, files, target = public_files(tmp_path)
    source = files["antall.csv"]
    source.chmod(stat.S_IREAD)
    try:
        publisher.publish(files, target)

        assert not (target / "antall.csv").stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
    finally:
        source.chmod(stat.S_IWRITE)
        delivered = target / "antall.csv"
        if delivered.exists():
            delivered.chmod(stat.S_IWRITE)


def test_public_blocked_rollback_retains_old_backups_and_original_candidates(tmp_path, monkeypatch):
    from molstat.failures import RunFailure
    fast_retries(monkeypatch)
    publisher, files, target = public_files(tmp_path)
    original = os.replace

    def denied(source, destination):
        if Path(source).suffix == ".bak" or (
            Path(source).suffix == ".tmp" and Path(destination).name == "resultater.csv"
        ):
            raise PermissionError(errno.EACCES, "PRIVATE-LOCK")
        return original(source, destination)

    monkeypatch.setattr(os, "replace", denied)

    with pytest.raises(RunFailure) as failure:
        publisher.publish(files, target)

    assert failure.value.code == "PUBLICATION_RECOVERY"
    assert "PRIVATE" not in str(failure.value)
    assert any(path.read_bytes().startswith(b"OLD-") for path in target.glob("*.bak"))
    assert all(path.exists() for path in files.values())


@pytest.mark.parametrize("after_backup", [False, True])
def test_public_ambiguous_rename_is_not_retried_and_restores_the_previous_set(tmp_path, monkeypatch, after_backup):
    pauses = fast_retries(monkeypatch)
    publisher, files, target = public_files(tmp_path)
    before = {name: (target / name).read_bytes() for name in files}
    original = os.replace
    ambiguous = []

    def completed_then_failed(source, destination):
        result = original(source, destination)
        chosen = Path(destination).suffix == ".bak" if after_backup else (
            Path(source).suffix == ".tmp" and Path(destination).name == "resultater.csv"
        )
        if chosen and not ambiguous:
            ambiguous.append(1)
            raise OSError(errno.EIO, "PRIVATE-UNCERTAIN-RENAME")
        return result

    monkeypatch.setattr(os, "replace", completed_then_failed)

    with pytest.raises(OSError) as failure:
        publisher.publish(files, target)

    assert failure.value.errno == errno.EIO
    assert pauses == []
    assert {name: (target / name).read_bytes() for name in files} == before
    assert all(path.exists() for path in files.values())


def test_private_ambiguous_rename_is_not_retried_and_restores_the_previous_set(tmp_path, monkeypatch):
    pauses = fast_retries(monkeypatch)
    publisher, files, target = public_files(tmp_path)
    before = {name: (target / name).read_bytes() for name in files}
    original = os.replace
    ambiguous = []

    def completed_then_failed(source, destination):
        result = original(source, destination)
        if Path(destination).name == "resultater.csv" and not ambiguous:
            ambiguous.append(1)
            raise OSError(errno.EIO, "PRIVATE-UNCERTAIN-RENAME")
        return result

    monkeypatch.setattr(os, "replace", completed_then_failed)

    with pytest.raises(OSError) as failure:
        install_private_files(files, target)

    assert failure.value.errno == errno.EIO
    assert pauses == []
    assert {name: (target / name).read_bytes() for name in files} == before
    assert all(path.exists() for path in files.values())


def test_private_staging_retries_before_replacing_any_target(tmp_path, monkeypatch):
    pauses = fast_retries(monkeypatch)
    publisher, files, target = public_files(tmp_path)
    from molstat import private_delivery
    original = private_delivery._copy
    copied = []

    def denied_once(source, destination):
        copied.append(Path(source))
        if len(copied) == 1:
            raise PermissionError(errno.EACCES, "PRIVATE-LOCK")
        return original(source, destination)

    monkeypatch.setattr(private_delivery, "_copy", denied_once)

    install_private_files(files, target)

    assert len(pauses) == 1
    assert all((target / name).read_bytes() == source.read_bytes() for name, source in files.items())


@pytest.mark.parametrize("private", [False, True])
def test_cancellation_during_install_still_restores_previous_file_set(tmp_path, monkeypatch, private):
    from molstat.failures import RunFailure
    from molstat.recovery import recovery_context
    fast_retries(monkeypatch)
    publisher, files, target = public_files(tmp_path)
    before = {name: (target / name).read_bytes() for name in files}
    cancel = Event()
    original = os.replace

    def cancel_second_install(source, destination):
        if Path(destination).name == "resultater.csv" and Path(source).suffix == ".tmp":
            cancel.set()
            raise PermissionError(errno.EACCES, "PRIVATE-LOCK")
        return original(source, destination)

    monkeypatch.setattr(os, "replace", cancel_second_install)
    with recovery_context(cancel=cancel), pytest.raises(RunFailure) as failure:
        if private:
            install_private_files(files, target)
        else:
            publisher.publish(files, target)

    assert failure.value.code == "CANCELLED"
    assert {name: (target / name).read_bytes() for name in files} == before
    assert all(path.exists() for path in files.values())


@pytest.mark.parametrize("cancel_after_move", [False, True])
def test_private_access_error_after_completed_move_restores_current_and_prior_files(tmp_path, monkeypatch, cancel_after_move):
    from molstat.failures import RunFailure
    from molstat.recovery import recovery_context
    fast_retries(monkeypatch)
    publisher, files, target = public_files(tmp_path)
    before = {name: (target / name).read_bytes() for name in files}
    original = os.replace
    cancel = Event()
    failed = []

    def moved_then_denied(source, destination):
        result = original(source, destination)
        if Path(destination).name == "resultater.csv" and not failed:
            failed.append(1)
            if cancel_after_move:
                cancel.set()
            raise PermissionError(errno.EACCES, "PRIVATE-ALREADY-MOVED")
        return result

    monkeypatch.setattr(os, "replace", moved_then_denied)
    with recovery_context(cancel=cancel), pytest.raises(RunFailure) as failure:
        install_private_files(files, target)

    assert failure.value.code in {"PRIVATE_FILES_LOCKED", "CANCELLED"}
    assert {name: (target / name).read_bytes() for name in files} == before
    assert all(path.exists() for path in files.values())
