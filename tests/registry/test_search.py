from datetime import datetime
from pathlib import Path

from molstat.database import MolStatDatabase
from molstat.registry import OccurrenceInput, SampleRegistry


def populated_registry(tmp_path: Path) -> tuple[SampleRegistry, str]:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    store = SampleRegistry(database)
    first = store.register_occurrence(
        OccurrenceInput(
            source_system="LVMS",
            sample_number="001230",
            analysis_code="CALR-OU",
            ordered_at=datetime(2026, 9, 10, 8, 0),
            source_occurrence_id="WORK-1",
            source_kind="backlog",
        ),
        observed_at=datetime(2026, 9, 10, 10, 0),
    )
    store.register_occurrence(
        OccurrenceInput(
            source_system="LVMS",
            sample_number="001231",
            analysis_code="JAK2-OU",
            ordered_at=datetime(2026, 9, 10, 9, 0),
            source_occurrence_id="WORK-2",
            source_kind="statistics_ordered",
        ),
        observed_at=datetime(2026, 9, 10, 10, 0),
    )
    return store, first.molstat_key


def test_exact_search_finds_sample_number_or_molstat_key(tmp_path: Path) -> None:
    store, molstat_key = populated_registry(tmp_path)

    by_sample = store.search("001230")
    by_molstat = store.search(molstat_key.lower())

    assert [item.sample_number for item in by_sample] == ["001230"]
    assert [item.molstat_key for item in by_molstat] == [molstat_key]
    assert [item.analysis_code for item in by_sample[0].occurrences] == ["CALR-OU"]


def test_prefix_search_returns_all_matching_samples(tmp_path: Path) -> None:
    store, _ = populated_registry(tmp_path)

    matches = store.search("00123", prefix=True)

    assert [item.sample_number for item in matches] == ["001230", "001231"]


def test_blank_search_returns_no_sensitive_rows(tmp_path: Path) -> None:
    store, _ = populated_registry(tmp_path)

    assert store.search("   ", prefix=True) == ()


def test_search_preserves_original_identifier_spelling(tmp_path: Path) -> None:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    store = SampleRegistry(database)
    store.register_occurrence(
        OccurrenceInput(
            source_system="LVMS",
            sample_number="ab-001",
            analysis_code="CALR-OU",
            ordered_at=datetime(2026, 9, 10, 8, 0),
            source_occurrence_id="WORK-1",
            source_kind="backlog",
        ),
        observed_at=datetime(2026, 9, 10, 10, 0),
    )

    assert store.search("AB-001")[0].sample_number == "ab-001"


def test_exact_search_uses_identifier_index(tmp_path: Path) -> None:
    store, _ = populated_registry(tmp_path)

    plan = store.explain_sample_number_search("001230")

    assert any("idx_sample_identifier_value" in detail for detail in plan)
