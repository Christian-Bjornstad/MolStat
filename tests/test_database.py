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

    assert database.schema_version() == 7
    assert database.table_names() == {
        "analysis_event",
        "analysis_occurrence",
        "backlog_current",
        "backlog_snapshot",
        "backlog_detail_snapshot",
        "backlog_sample",
        "import_run",
        "job_run",
        "raw_file",
        "sample",
        "sample_identifier",
        "schema_info",
        "source_observation",
        "statistics_publication",
        "writer_lease",
    }


def test_schema_probe_does_not_create_a_database(tmp_path: Path) -> None:
    path = tmp_path / "molstat.sqlite3"

    assert MolStatDatabase(path).schema_version_if_present() is None
    assert not path.exists()


def test_second_pc_can_probe_schema_while_first_pc_has_write_reservation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "molstat.sqlite3"
    first = MolStatDatabase(path)
    second = MolStatDatabase(path)
    first.migrate()

    with first._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            assert second.schema_version_if_present() == 7
        finally:
            connection.execute("ROLLBACK")


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

    assert database.schema_version() == 7
    assert "backlog_snapshot" in database.table_names()
    assert "backlog_detail_snapshot" in database.table_names()
    with database._connect() as connection:
        row = connection.execute(
            "SELECT sample_key, analysis_group FROM backlog_sample"
        ).fetchone()
    assert row == ("preserved-key", "KLONALITET")


def test_v3_migration_adds_approved_text_columns_with_empty_history(
    tmp_path: Path,
) -> None:
    path = tmp_path / "molstat.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info(version) VALUES (3)")
        connection.execute(
            """
            CREATE TABLE backlog_detail_snapshot (
                observed_at TEXT NOT NULL,
                unit_key TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                material TEXT NOT NULL,
                analysis_code TEXT NOT NULL,
                nucleic_acid TEXT NOT NULL,
                report_group TEXT NOT NULL,
                analysis_group_code TEXT NOT NULL,
                analysis_group_label TEXT NOT NULL,
                collected_at TEXT,
                arrived_at TEXT,
                ordered_at TEXT NOT NULL,
                analysis_priority TEXT NOT NULL,
                request_priority TEXT NOT NULL,
                analysis_status TEXT NOT NULL,
                preliminary_status TEXT NOT NULL,
                workflow_stage TEXT NOT NULL,
                response_deadline TEXT NOT NULL,
                classifier_version INTEGER NOT NULL,
                source_fingerprint TEXT NOT NULL,
                PRIMARY KEY (observed_at, unit_key, row_number, classifier_version)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO backlog_detail_snapshot VALUES
            ('2026-09-07T10:00:00', 'hemato', 1, 'Blod', 'A', 'DNA',
             'legacy', 'A', 'Analyse A', NULL, NULL, '2026-09-07T09:00:00',
             '', '', 'Initial', 'Initial', 'ready', '14', 2, 'fingerprint')
            """
        )

    database = MolStatDatabase(path)
    database.migrate()

    assert database.schema_version() == 7
    with database._connect() as connection:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(backlog_detail_snapshot)"
            )
        }
        text_fields = connection.execute(
            """
            SELECT analysis_result, external_analysis_comment, molstat_key
            FROM backlog_detail_snapshot
            """
        ).fetchone()
    assert {"analysis_result", "external_analysis_comment", "molstat_key"} <= columns
    assert text_fields == ("", "", "")


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
