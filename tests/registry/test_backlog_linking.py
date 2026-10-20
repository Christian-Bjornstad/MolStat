from datetime import date, datetime
from pathlib import Path

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
from molstat.registry import AmbiguousOccurrenceError


def _processor(now: datetime) -> BacklogProcessor:
    config = AppConfig(
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
    contract = CsvContract(
        delimiter=";",
        encoding="cp1252",
        columns={
            "sample_id": "SampleID",
            "occurrence_id": "WorkItem",
            "analysis_code": "Analyse",
            "created_at": "Tidspunkt analysebestilling",
            "arrival_at": "Tidspunkt ankomst",
            "status": "Status analyse",
        },
        completed_values=("Completed",),
    )
    return BacklogProcessor(config, contract, now=lambda: now)


def _write(path: Path, *rows: tuple[str, str, str]) -> None:
    lines = [
        "SampleID;WorkItem;Analyse;Tidspunkt analysebestilling;"
        "Tidspunkt ankomst;Status analyse"
    ]
    lines.extend(
        f"{sample};{workitem};IGH-OU;{ordered};30.08.2026 08:00;Initial"
        for sample, workitem, ordered in rows
    )
    path.write_text("\n".join(lines) + "\n", encoding="cp1252")


def _import(processor: BacklogProcessor, path: Path, database: MolStatDatabase) -> None:
    processor.import_snapshot(
        path,
        database,
        date_from=date(2024, 1, 1),
        date_to=date(2026, 9, 10),
    )


def test_backlog_preserves_repeated_analysis_occurrences_and_permanent_history(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    _write(
        first,
        ("S-1", "WORK-1", "30.08.2026 07:00"),
        ("S-1", "WORK-2", "31.08.2026 07:00"),
    )
    _write(second, ("S-1", "WORK-2", "31.08.2026 07:00"))
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    processor = _processor(datetime(2026, 9, 10, 10, 0))

    _import(processor, first, database)
    with database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM analysis_occurrence"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM backlog_current"
        ).fetchone()[0] == 2

    _import(processor, second, database)

    with database._connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM backlog_current"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM analysis_occurrence"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM source_observation WHERE source_kind = 'backlog'"
        ).fetchone()[0] == 2


def test_registry_collision_rolls_back_backlog_current_and_import_run(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.csv"
    conflicting = tmp_path / "conflicting.csv"
    _write(first, ("S-1", "WORK-1", "30.08.2026 07:00"))
    _write(conflicting, ("S-2", "WORK-1", "30.08.2026 07:00"))
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    processor = _processor(datetime(2026, 9, 10, 10, 0))
    _import(processor, first, database)

    with pytest.raises(AmbiguousOccurrenceError):
        _import(processor, conflicting, database)

    with database._connect() as connection:
        current = connection.execute(
            """
            SELECT si.identifier_value
            FROM backlog_current AS bc
            JOIN analysis_occurrence AS ao ON ao.id = bc.occurrence_id
            JOIN sample_identifier AS si ON si.sample_id = ao.sample_id
            """
        ).fetchall()
        run_count = connection.execute("SELECT COUNT(*) FROM import_run").fetchone()[0]
        sample_count = connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0]
    assert current == [("S-1",)]
    assert run_count == 1
    assert sample_count == 1


def test_empty_backlog_file_keeps_previous_current_state(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    empty = tmp_path / "empty.csv"
    _write(first, ("S-1", "WORK-1", "30.08.2026 07:00"))
    _write(empty)
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    processor = _processor(datetime(2026, 9, 10, 10, 0))
    _import(processor, first, database)

    from molstat.backlog import CsvImportError

    with pytest.raises(CsvImportError, match="ingen datarader"):
        _import(processor, empty, database)

    with database._connect() as connection:
        current_count = connection.execute(
            "SELECT COUNT(*) FROM backlog_current"
        ).fetchone()[0]
        run_count = connection.execute("SELECT COUNT(*) FROM import_run").fetchone()[0]
    assert current_count == 1
    assert run_count == 1
