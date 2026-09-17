from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from molstat.backlog import (
    AnalysisConfig,
    AppConfig,
    BacklogProcessor,
    CsvContract,
    ThresholdsConfig,
    UnitConfig,
)
from molstat.database import MolStatDatabase


def _config() -> AppConfig:
    return AppConfig(
        report_id="PAT-DIT-RESTANSE-OU",
        unit=UnitConfig(key="hemato", label="MolPat hemato"),
        thresholds=ThresholdsConfig(warning_hours=24, critical_hours=48),
        analyses=(
            AnalysisConfig(
                code="KLONALITET",
                label="Klonalitet",
                group="Molekylær",
                priority="standard",
                source_codes=("IGH-OU",),
            ),
        ),
    )


def _contract() -> CsvContract:
    return CsvContract(
        delimiter=";",
        encoding="cp1252",
        columns={
            "sample_id": "SampleID",
            "analysis_code": "Analyse",
            "created_at": "Tidspunkt analysebestilling",
            "arrival_at": "Tidspunkt ankomst",
            "status": "Status analyse",
            "result": "Analyseresultat",
            "external_comment": "Ekstern analysekommentar",
        },
        completed_values=("Completed",),
    )


def test_processor_replaces_sensitive_snapshot_and_exposes_only_aggregates(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "restanse.csv"
    csv_path.write_text(
        "SampleID;Analyse;Tidspunkt analysebestilling;Tidspunkt ankomst;"
        "Status analyse;Analyseresultat\n"
        "SECRET-SAMPLE-42;IGH-OU;30.08.2026 07:00;30.08.2026 08:00;"
        "Initial;\n",
        encoding="cp1252",
    )
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    observed_at = datetime(2026, 9, 2, 8, 0)
    processor = BacklogProcessor(
        _config(), _contract(), now=lambda: observed_at
    )

    imported = processor.import_snapshot(csv_path, database)
    snapshot = processor.public_snapshot(
        database, observed_at + timedelta(hours=1)
    )

    assert imported.rows_read == 1
    assert snapshot["totals"] == {
        "ready": 1,
        "awaitingApproval": 0,
        "inTransit": 0,
        "overdue": 1,
    }
    serialized = repr(snapshot)
    for forbidden in (
        "SECRET-SAMPLE-42",
        "SampleID",
        "PID",
        "WorkItem",
        str(tmp_path),
    ):
        assert forbidden not in serialized


def _write_snapshot(path: Path, sample_id: str) -> None:
    path.write_text(
        "SampleID;Analyse;Tidspunkt analysebestilling;Tidspunkt ankomst;"
        "Status analyse;Analyseresultat\n"
        f"{sample_id};IGH-OU;30.08.2026 07:00;30.08.2026 08:00;Initial;\n",
        encoding="cp1252",
    )


def test_invalid_snapshot_does_not_replace_current_state(tmp_path):
    path = tmp_path / "source.csv"
    _write_snapshot(path, "SYNTHETIC")
    database = MolStatDatabase(tmp_path / "db.sqlite3")
    database.migrate()
    processor = BacklogProcessor(_config(), _contract())
    processor.import_snapshot(path, database)
    with database._connect() as connection:
        previous = connection.execute("SELECT * FROM backlog_current").fetchall()
    path.write_text("SampleID;Analyse;Tidspunkt analysebestilling;Status analyse\nSYNTHETIC;IGH-OU;bad-date;Initial\n", encoding="cp1252")
    with pytest.raises(ValueError, match="ugyldige"):
        processor.import_snapshot(path, database)
    with database._connect() as connection:
        assert connection.execute("SELECT * FROM backlog_current").fetchall() == previous


def test_processor_retains_one_aggregate_row_per_group_and_hour(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "restanse.csv"
    _write_snapshot(csv_path, "SYNTHETIC-1")
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    processor = BacklogProcessor(
        _config(), _contract(), now=lambda: datetime(2026, 9, 7, 11, 42)
    )

    processor.import_snapshot(csv_path, database)
    processor.import_snapshot(csv_path, database)

    with database._connect() as connection:
        rows = connection.execute(
            "SELECT observed_at, analysis_code FROM backlog_snapshot"
        ).fetchall()
        detail_rows = connection.execute(
            "SELECT observed_at, analysis_code FROM backlog_detail_snapshot"
        ).fetchall()
    assert rows == [("2026-09-07T11:00:00", "KLONALITET")]
    assert detail_rows == [("2026-09-07T11:00:00", "IGH-OU")]


def test_processor_persists_pseudonymous_detail_with_statistics_metadata(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "restanse.csv"
    csv_path.write_text(
        "SampleID;Analyse;Tidspunkt analysebestilling;Tidspunkt ankomst;"
        "Status analyse;Analyseresultat;Ekstern analysekommentar\n"
        "SECRET-42;IGH-OU;30.08.2026 07:00;30.08.2026 08:00;Initial;"
        "Påvist – test;Ordrett vurdering\n",
        encoding="cp1252",
    )
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    processor = BacklogProcessor(
        _config(),
        _contract(),
        now=lambda: datetime(2026, 9, 7, 11, 42),
        analysis_lookup={
            "IGH-OU": {
                "Nukleinsyre": "DNA",
                "Rapportgruppe": "lymfom",
                "Svarfrist": "14",
            }
        },
    )

    processor.import_snapshot(csv_path, database)

    with database._connect() as connection:
        row = connection.execute(
            """
            SELECT analysis_code, nucleic_acid, report_group,
                   analysis_group_code, analysis_group_label, response_deadline,
                   analysis_result, external_analysis_comment, molstat_key
            FROM backlog_detail_snapshot
            """
        ).fetchone()
        columns = {
            str(item[1])
            for item in connection.execute(
                "PRAGMA table_info(backlog_detail_snapshot)"
            ).fetchall()
        }
    assert row == (
        "IGH-OU",
        "DNA",
        "",
        "KLONALITET",
        "Klonalitet",
        "14",
        "Påvist – test",
        "Ordrett vurdering",
        "M-000001",
    )
    assert "sample_id" not in columns
    assert "pid" not in columns
    assert "workitem" not in columns


def test_history_failure_rolls_back_current_sensitive_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    _write_snapshot(first, "PRESERVED-SYNTHETIC")
    _write_snapshot(second, "REJECTED-SYNTHETIC")
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    processor = BacklogProcessor(
        _config(), _contract(), now=lambda: datetime(2026, 9, 7, 11, 42)
    )
    processor.import_snapshot(first, database)

    from molstat._backlog.history import build_history_rows as real_build

    def invalid_history(*args, **kwargs):
        rows = real_build(*args, **kwargs)
        return (replace(rows[0], ready_count=-1),)

    monkeypatch.setattr("molstat.backlog.build_history_rows", invalid_history)

    with pytest.raises(sqlite3.IntegrityError):
        processor.import_snapshot(second, database)

    with database._connect() as connection:
        current = connection.execute(
            "SELECT sample_key FROM backlog_sample"
        ).fetchall()
        snapshot_count = connection.execute(
            "SELECT COUNT(*) FROM backlog_snapshot"
        ).fetchone()[0]
    assert current == [("PRESERVED-SYNTHETIC",)]
    assert snapshot_count == 1
