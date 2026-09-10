from datetime import date, datetime
from pathlib import Path
from time import perf_counter

from molstat.database import MolStatDatabase
from molstat.registry import OccurrenceInput, RegistryImportItem, SampleRegistry


SAMPLE_COUNT = 300_000
OCCURRENCES_PER_SAMPLE = 2


def _synthetic_occurrences():
    for sample_index in range(SAMPLE_COUNT):
        sample_number = f"V{sample_index:09d}"
        for occurrence_index in range(OCCURRENCES_PER_SAMPLE):
            yield RegistryImportItem(
                OccurrenceInput(
                    source_system="LVMS",
                    sample_number=sample_number,
                    analysis_code=f"SYNTH-{occurrence_index}",
                    ordered_at=datetime(2026, 1, 1, 8 + occurrence_index),
                    source_occurrence_id=(
                        f"W{sample_index:09d}-{occurrence_index}"
                    ),
                    source_kind="statistics_ordered",
                )
            )


def test_ten_year_volume_imports_without_collisions_and_searches_by_index(
    tmp_path: Path,
) -> None:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    registry = SampleRegistry(database)

    import_started = perf_counter()
    registry.import_batch(
        _synthetic_occurrences(),
        row_count=SAMPLE_COUNT * OCCURRENCES_PER_SAMPLE,
        kind="statistics",
        unit_key="synthetic",
        date_from=date(2017, 1, 1),
        date_to=date(2026, 12, 31),
        observed_at=datetime(2026, 12, 31, 12, 0),
        source_fingerprint="synthetic-volume",
    )
    import_seconds = perf_counter() - import_started

    search_started = perf_counter()
    result = registry.search("V000299999")
    search_seconds = perf_counter() - search_started
    print(
        f"volume import={import_seconds:.3f}s search={search_seconds:.6f}s "
        f"samples={SAMPLE_COUNT} occurrences={SAMPLE_COUNT * OCCURRENCES_PER_SAMPLE}"
    )

    with database._connect() as connection:
        sample_count = connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0]
        occurrence_count = connection.execute(
            "SELECT COUNT(*) FROM analysis_occurrence"
        ).fetchone()[0]
        unique_keys = connection.execute(
            "SELECT COUNT(DISTINCT molstat_key) FROM sample"
        ).fetchone()[0]
    assert sample_count == SAMPLE_COUNT
    assert occurrence_count == SAMPLE_COUNT * OCCURRENCES_PER_SAMPLE
    assert unique_keys == SAMPLE_COUNT
    assert len(result) == 1
    assert len(result[0].occurrences) == OCCURRENCES_PER_SAMPLE
    assert any("INDEX" in step.upper() for step in registry.explain_sample_number_search(
        "V000299999"
    ))
    assert import_seconds < 180
    assert search_seconds < 2
