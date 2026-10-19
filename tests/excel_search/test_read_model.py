from datetime import datetime
from pathlib import Path

from molstat.excel_search import read_excel_snapshot

from .helpers import populated_database


def test_read_model_reconciles_samples_occurrences_and_current_backlog(
    tmp_path: Path,
) -> None:
    database = populated_database(tmp_path / "molstat.sqlite3")

    snapshot = read_excel_snapshot(
        database,
        generated_at=datetime(2026, 9, 10, 12, 30),
    )

    assert len(snapshot.samples) == 1
    assert len(snapshot.analyses) == 2
    assert snapshot.samples[0].sample_number == "00123456789012345678"
    assert snapshot.samples[0].occurrence_count == 2
    assert snapshot.samples[0].backlog_count == 1
    assert [row.in_backlog for row in snapshot.analyses] == [False, True]
    assert snapshot.analyses[0].approved_at == datetime(2026, 9, 9, 10, 0)


def test_excel_snapshot_does_not_write_during_an_active_writer_lease(tmp_path, monkeypatch):
    """A reader must not renew the writer token through a read-only connection."""
    import sqlite3
    from datetime import timedelta
    from molstat.database import ManagedConnection, readonly_uri
    from molstat._writer_lease import active_writer_lease

    database = populated_database(tmp_path / "molstat.sqlite3")
    with database.writer_lease("synthetic-pc", timedelta(minutes=5), renew=True):
        def readonly_writer_connection(**kwargs):
            connection = sqlite3.connect(readonly_uri(database.path), uri=True,
                isolation_level=None, factory=ManagedConnection)
            connection._writer_guard = active_writer_lease(database.path)
            return connection

        with monkeypatch.context() as patch:
            patch.setattr(database, "_connect", readonly_writer_connection)
            snapshot = read_excel_snapshot(database, generated_at=datetime(2026, 10, 19))
        assert len(snapshot.samples) == 1
        assert len(snapshot.analyses) == 2


def test_read_connection_never_creates_a_missing_database(tmp_path):
    import pytest
    import sqlite3
    from molstat.database import MolStatDatabase

    database = MolStatDatabase(tmp_path / "missing" / "molstat.sqlite3")
    with pytest.raises(sqlite3.OperationalError):
        database.read_connection()
    assert not database.path.exists()
