from datetime import datetime
from pathlib import Path

from molstat.database import MolStatDatabase
from molstat.registry import OccurrenceInput, SampleRegistry
from molstat.statistics import StatisticsProcessor


def _write_report(path: Path, header: str, row: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{header}\n{row}\n", encoding="cp1252")


def test_statistics_links_all_sources_idempotently_without_changing_exports(
    tmp_path: Path, monkeypatch
) -> None:
    archive = tmp_path / "raw" / "statistics" / "hemato"
    ordered = archive / "PAT-DIT-ANTALL-OU__2026-09-05__2026-09-10.csv"
    answered = archive / "PAT-DIT-RESULTATER-OU__2026-09-05__2026-09-10.csv"
    extraction = archive / "PAT-DIT-EKSTRAKSJON-OU__2026-09-05__2026-09-10.csv"
    _write_report(
        ordered,
        "Sample ID;WorkItem;Analyse;Tidspunkt analysebestilling;Tidspunkt opprettet",
        'S-1;W-CALR;CALR-OU;08.09.2026 08:00;08.09.2026 07:30',
    )
    _write_report(
        answered,
        "Sample ID;WorkItem;Analyse;Tidspunkt analysebestilling;"
        "Tidspunkt analyseresultat;Tidspunkt godkjenning",
        'S-1;W-CALR;CALR-OU;08.09.2026 08:00;09.09.2026 09:00;09.09.2026 10:00',
    )
    _write_report(
        extraction,
        "Sample ID;WorkItem;Analyse;Tidspunkt analysebestilling;"
        "Tidspunkt analyseresultat;Tidspunkt godkjenning",
        'S-1;W-EXT;EKSTRAAPKOL-H-OU;08.09.2026 08:15;08.09.2026 10:00;08.09.2026 10:30',
    )

    def deterministic_exports(*args, **kwargs):
        output_dir = args[4]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "antall.csv").write_bytes(b"Analyse\r\nCALR-OU\r\n")
        (output_dir / "resultater.csv").write_bytes(b"Analyse\r\nCALR-OU\r\n")
        return {"antall": 1, "resultater": 1}

    monkeypatch.setattr("molstat.statistics.process_reports", deterministic_exports)
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    existing = SampleRegistry(database).register_occurrence(
        OccurrenceInput(
            source_system="LVMS",
            sample_number="S-1",
            analysis_code="CALR-OU",
            ordered_at=datetime(2026, 9, 8, 8, 0),
            source_occurrence_id="W-CALR",
            source_kind="backlog",
        ),
        observed_at=datetime(2026, 9, 8, 9, 0),
    )
    processor = StatisticsProcessor(
        tmp_path / "unused.xlsx",
        database=database,
        now=lambda: datetime(2026, 9, 10, 12, 0),
    )

    first = processor.process("hemato", (ordered, answered, extraction), tmp_path / "out1")
    second = processor.process("hemato", (ordered, answered, extraction), tmp_path / "out2")

    assert first.antall.read_bytes() == second.antall.read_bytes()
    assert first.resultater.read_bytes() == second.resultater.read_bytes()
    with database._connect() as connection:
        sample_count = connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0]
        occurrence_rows = connection.execute(
            "SELECT id, analysis_code FROM analysis_occurrence ORDER BY analysis_code"
        ).fetchall()
        event_count = connection.execute("SELECT COUNT(*) FROM analysis_event").fetchone()[0]
        observation_count = connection.execute(
            "SELECT COUNT(*) FROM source_observation"
        ).fetchone()[0]
        statistics_runs = connection.execute(
            "SELECT COUNT(*) FROM import_run WHERE kind = 'statistics'"
        ).fetchone()[0]
    assert sample_count == 1
    assert {row[1] for row in occurrence_rows} == {"CALR-OU", "EKSTRAAPKOL-H-OU"}
    assert existing.occurrence_id in {row[0] for row in occurrence_rows}
    assert event_count == 6
    assert observation_count == 4
    assert statistics_runs == 2
