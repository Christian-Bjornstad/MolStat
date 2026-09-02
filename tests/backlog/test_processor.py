from datetime import datetime, timedelta
from pathlib import Path

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
