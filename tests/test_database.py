from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from molstat.database import MolStatDatabase, WriterLeaseBusy


class Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def test_database_migration_is_idempotent(tmp_path: Path) -> None:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")

    database.migrate()
    database.migrate()

    assert database.schema_version() == 2
    assert database.table_names() == {
        "backlog_snapshot",
        "backlog_sample",
        "job_run",
        "raw_file",
        "schema_info",
        "statistics_publication",
        "writer_lease",
    }


def test_v1_migration_adds_history_without_rewriting_current_samples(
    tmp_path: Path,
) -> None:
    path = tmp_path / "molstat.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info(version) VALUES (1)")
        connection.execute(
            """
            CREATE TABLE backlog_sample (
                sample_key TEXT NOT NULL,
                analysis_group TEXT NOT NULL,
                ordered_at TEXT NOT NULL,
                arrived_at TEXT,
                workflow_stage TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY (sample_key, analysis_group)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO backlog_sample VALUES
            ('preserved-key', 'KLONALITET', '2026-09-07T08:00:00', NULL,
             'in_transit', '2026-09-07T09:00:00')
            """
        )

    database = MolStatDatabase(path)
    database.migrate()

    assert database.schema_version() == 2
    assert "backlog_snapshot" in database.table_names()
    with database._connect() as connection:
        row = connection.execute(
            "SELECT sample_key, analysis_group FROM backlog_sample"
        ).fetchone()
    assert row == ("preserved-key", "KLONALITET")


def test_second_writer_is_rejected_while_lease_is_active(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc))
    database = MolStatDatabase(tmp_path / "molstat.sqlite3", now=clock)
    database.migrate()

    with database.writer_lease("pc-a", timedelta(minutes=30)):
        with pytest.raises(WriterLeaseBusy, match="pc-a"):
            with database.writer_lease("pc-b", timedelta(minutes=30)):
                pass


def test_second_writer_can_take_over_after_expiry(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc))
    first = MolStatDatabase(tmp_path / "molstat.sqlite3", now=clock)
    second = MolStatDatabase(tmp_path / "molstat.sqlite3", now=clock)
    first.migrate()

    with first.writer_lease("pc-a", timedelta(minutes=30)):
        clock.current += timedelta(minutes=31)
        with second.writer_lease("pc-b", timedelta(minutes=30)):
            assert second.current_lease_owner() == "pc-b"
        assert second.current_lease_owner() is None


def test_expired_owner_cannot_release_replacement_lease(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc))
    first = MolStatDatabase(tmp_path / "molstat.sqlite3", now=clock)
    second = MolStatDatabase(tmp_path / "molstat.sqlite3", now=clock)
    first.migrate()

    first_context = first.writer_lease("pc-a", timedelta(minutes=1))
    first_context.__enter__()
    clock.current += timedelta(minutes=2)
    second_context = second.writer_lease("pc-b", timedelta(minutes=30))
    second_context.__enter__()

    first_context.__exit__(None, None, None)

    assert second.current_lease_owner() == "pc-b"
    second_context.__exit__(None, None, None)
