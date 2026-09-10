from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from molstat.backup import (
    BackupIntegrityError,
    backup_before_migration,
    create_verified_backup,
    restore_verified_backup,
    verify_database_file,
)
from molstat.database import MolStatDatabase
from molstat.registry import (
    OccurrenceEventInput,
    OccurrenceInput,
    RegistryImportItem,
    SampleRegistry,
)


def _populated_database(path: Path) -> MolStatDatabase:
    database = MolStatDatabase(path)
    database.migrate()
    registry = SampleRegistry(database)
    run_id = registry.import_batch(
        (
            RegistryImportItem(
                OccurrenceInput(
                    source_system="LVMS",
                    sample_number="SYNTHETIC-001",
                    analysis_code="CALR-OU",
                    ordered_at=datetime(2026, 9, 10, 8, 0),
                    source_occurrence_id="WORK-001",
                    source_kind="backlog",
                ),
                (OccurrenceEventInput("ordered", datetime(2026, 9, 10, 8, 0)),),
            ),
        ),
        kind="backlog",
        unit_key="hemato",
        date_from=date(2024, 1, 1),
        date_to=date(2026, 9, 10),
        observed_at=datetime(2026, 9, 10, 9, 0),
        source_fingerprint="synthetic",
    )
    with database._connect() as connection:
        occurrence_id = connection.execute(
            "SELECT id FROM analysis_occurrence"
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO backlog_current(
                occurrence_id, import_run_id, unit_key, analysis_group,
                workflow_stage, updated_at
            ) VALUES (?, ?, 'hemato', 'CALR', 'ready', ?)
            """,
            (occurrence_id, run_id, datetime(2026, 9, 10, 9, 0).isoformat()),
        )
    return database


def test_verified_backup_restores_registry_and_passes_integrity_check(
    tmp_path: Path,
) -> None:
    database = _populated_database(tmp_path / "data" / "molstat.sqlite3")

    backup = create_verified_backup(
        database,
        tmp_path / "data" / "backups",
        now=lambda: datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
    )
    restored_path = tmp_path / "restore" / "molstat.sqlite3"
    restore_verified_backup(backup.path, restored_path)

    assert backup.path.parent == tmp_path / "data" / "backups"
    assert backup.integrity_result == "ok"
    assert verify_database_file(restored_path) == "ok"
    with sqlite3.connect(restored_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM analysis_occurrence"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM source_observation"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM analysis_event"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM backlog_current"
        ).fetchone()[0] == 1


def test_corrupt_backup_is_rejected_before_restore(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not a sqlite database")

    with pytest.raises(BackupIntegrityError):
        verify_database_file(corrupt)
    with pytest.raises(BackupIntegrityError):
        restore_verified_backup(corrupt, tmp_path / "restore.sqlite3")

    assert not (tmp_path / "restore.sqlite3").exists()


def test_validation_of_stable_backup_does_not_depend_on_sqlite_file_locks(
    tmp_path: Path,
) -> None:
    """A completed backup must remain readable on shares with stale locks."""

    database_path = tmp_path / "molstat.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('preserved')")

    lock = sqlite3.connect(database_path)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        assert verify_database_file(database_path) == "ok"
    finally:
        lock.rollback()
        lock.close()


def test_validation_error_exposes_safe_sqlite_error_code(
    tmp_path: Path,
) -> None:
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not a sqlite database")

    with pytest.raises(BackupIntegrityError, match="SQLITE_NOTADB"):
        verify_database_file(corrupt)


def test_backup_before_migration_runs_once_for_an_older_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "molstat.sqlite3"
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE schema_info(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info(version) VALUES (4)")
        connection.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel(value) VALUES ('preserved')")
    database = MolStatDatabase(database_path)

    backup = backup_before_migration(database, tmp_path / "data" / "backups")
    assert backup is not None
    with sqlite3.connect(backup.path) as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchone() == (
            "preserved",
        )

    database.migrate()
    assert backup_before_migration(database, tmp_path / "data" / "backups") is None
