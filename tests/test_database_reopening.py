"""Database reopening regressions using synthetic files only."""

from contextlib import closing
from pathlib import Path, PureWindowsPath
import sqlite3
from urllib.parse import unquote, urlsplit

import pytest

from molstat import backup
from molstat.database import MolStatDatabase, SCHEMA_VERSION


@pytest.mark.parametrize(
    "operation",
    ["schema_version_if_present", "migrate", "schema_version", "table_names"],
)
def test_database_operations_release_connection_before_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    path = tmp_path / "molstat.sqlite3"
    MolStatDatabase(path).migrate()
    original_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []

    def tracked_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        # Retain references so garbage collection cannot hide a leaked handle.
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    try:
        getattr(MolStatDatabase(path), operation)()

        assert opened
        for connection in opened:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connection.execute("SELECT 1")
    finally:
        for connection in opened:
            connection.close()


def test_schema_probe_closes_connection_when_database_is_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "molstat.sqlite3"
    path.write_bytes(b"synthetic corrupt database")
    original_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []

    def tracked_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            MolStatDatabase(path).schema_version_if_present()

        assert opened
        for connection in opened:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connection.execute("SELECT 1")
    finally:
        for connection in opened:
            connection.close()


@pytest.mark.parametrize("operation", ["schema_probe", "backup_verification"])
def test_existing_database_on_unc_share_can_be_opened_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    local_path = tmp_path / "synthetic.sqlite3"
    with closing(sqlite3.connect(local_path)) as connection:
        connection.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info VALUES (?)", (SCHEMA_VERSION,))
        connection.commit()

    class ExistingSharePath(PureWindowsPath):
        def resolve(self):
            return self

        def is_file(self):
            return True

    shared_path = ExistingSharePath(r"\\molstat-test-server\team share\data #1.sqlite3")
    original_connect = sqlite3.connect

    def connect_to_simulated_share(database, *args, **kwargs):
        # Model only network storage, preserving the SQLite URI contract.
        # Default SQLite builds reject non-localhost URI authorities before I/O.
        if kwargs.get("uri"):
            parsed = urlsplit(str(database))
            if parsed.netloc not in ("", "localhost"):
                raise sqlite3.OperationalError(
                    f"invalid uri authority: {parsed.netloc}"
                )
            assert unquote(parsed.path) == shared_path.as_posix()
            assert "mode=ro" in parsed.query
        else:
            assert PureWindowsPath(database) == shared_path
        return original_connect(local_path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect_to_simulated_share)
    if operation == "schema_probe":
        assert MolStatDatabase(shared_path).schema_version_if_present() == SCHEMA_VERSION
    else:
        monkeypatch.setattr(backup, "Path", lambda _: shared_path)
        assert backup.verify_database_file(shared_path) == "ok"
