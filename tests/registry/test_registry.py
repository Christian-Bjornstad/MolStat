from datetime import date, datetime
from pathlib import Path

import pytest

from molstat.database import MolStatDatabase
from molstat.registry import (
    AmbiguousOccurrenceError,
    OccurrenceInput,
    RegistryImportItem,
    SampleRegistry,
)


def registry(tmp_path: Path) -> SampleRegistry:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    return SampleRegistry(database)


def test_repeated_import_reuses_sample_and_occurrence(tmp_path: Path) -> None:
    store = registry(tmp_path)
    item = OccurrenceInput(
        source_system="LVMS",
        sample_number="00123",
        analysis_code="CALR-OU",
        ordered_at=datetime(2026, 9, 10, 8, 0),
        source_occurrence_id="WORK-1",
        source_kind="backlog",
    )

    first = store.register_occurrence(item, observed_at=datetime(2026, 9, 10, 9, 0))
    second = store.register_occurrence(item, observed_at=datetime(2026, 9, 10, 10, 0))

    assert first.sample_id == second.sample_id
    assert first.occurrence_id == second.occurrence_id
    assert first.molstat_key == second.molstat_key
    assert first.molstat_key == "M-000001"
    assert store.counts() == (1, 1)


def test_new_samples_receive_short_monotonic_molstat_ids(tmp_path: Path) -> None:
    store = registry(tmp_path)
    observed = datetime(2026, 9, 10, 10, 0)

    created = [
        store.register_occurrence(
            OccurrenceInput(
                source_system="LVMS",
                sample_number=f"S-{number}",
                analysis_code="CALR-OU",
                ordered_at=datetime(2026, 9, 10, 8, number),
                source_occurrence_id=f"WORK-{number}",
                source_kind="backlog",
            ),
            observed_at=observed,
        ).molstat_key
        for number in range(1, 4)
    ]

    assert created == ["M-000001", "M-000002", "M-000003"]


def test_deleted_unlinked_sample_id_is_not_reused(tmp_path: Path) -> None:
    store = registry(tmp_path)
    with store.database._connect() as connection:
        connection.execute(
            """
            INSERT INTO sample(molstat_key, first_seen_at, last_seen_at)
            VALUES ('M-000001', '2026-09-10T08:00:00', '2026-09-10T08:00:00')
            """
        )
        connection.execute("DELETE FROM sample WHERE molstat_key = 'M-000001'")

    registered = store.register_occurrence(
        OccurrenceInput(
            source_system="LVMS",
            sample_number="S-2",
            analysis_code="CALR-OU",
            ordered_at=datetime(2026, 9, 10, 9, 0),
            source_occurrence_id="WORK-2",
            source_kind="backlog",
        ),
        observed_at=datetime(2026, 9, 10, 10, 0),
    )

    assert registered.molstat_key == "M-000002"


def test_same_sample_can_have_repeated_analysis_occurrences(tmp_path: Path) -> None:
    store = registry(tmp_path)
    common = {
        "source_system": "LVMS",
        "sample_number": "S-1",
        "analysis_code": "CALR-OU",
        "source_kind": "statistics_answered",
    }

    first = store.register_occurrence(
        OccurrenceInput(
            **common,
            ordered_at=datetime(2026, 9, 10, 8, 0),
            source_occurrence_id="WORK-1",
        ),
        observed_at=datetime(2026, 9, 10, 10, 0),
    )
    second = store.register_occurrence(
        OccurrenceInput(
            **common,
            ordered_at=datetime(2026, 9, 10, 9, 0),
            source_occurrence_id="WORK-2",
        ),
        observed_at=datetime(2026, 9, 10, 10, 0),
    )

    assert first.sample_id == second.sample_id
    assert first.occurrence_id != second.occurrence_id
    assert store.counts() == (1, 2)


def test_source_occurrence_id_cannot_silently_move_to_another_sample(
    tmp_path: Path,
) -> None:
    store = registry(tmp_path)
    observed = datetime(2026, 9, 10, 10, 0)
    store.register_occurrence(
        OccurrenceInput(
            source_system="LVMS",
            sample_number="S-1",
            analysis_code="CALR-OU",
            ordered_at=datetime(2026, 9, 10, 8, 0),
            source_occurrence_id="WORK-1",
            source_kind="backlog",
        ),
        observed_at=observed,
    )

    with pytest.raises(AmbiguousOccurrenceError):
        store.register_occurrence(
            OccurrenceInput(
                source_system="LVMS",
                sample_number="S-2",
                analysis_code="CALR-OU",
                ordered_at=datetime(2026, 9, 10, 8, 0),
                source_occurrence_id="WORK-1",
                source_kind="backlog",
            ),
            observed_at=observed,
        )

    assert store.counts() == (1, 1)


def test_fallback_occurrence_is_flagged_for_quality_review(tmp_path: Path) -> None:
    store = registry(tmp_path)

    registered = store.register_occurrence(
        OccurrenceInput(
            source_system="LVMS",
            sample_number="S-1",
            analysis_code="CALR-OU",
            ordered_at=datetime(2026, 9, 10, 8, 0),
            source_kind="backlog",
        ),
        observed_at=datetime(2026, 9, 10, 10, 0),
    )

    assert registered.identity_status == "fallback_review"


def test_streamed_batch_row_count_mismatch_rolls_back(tmp_path: Path) -> None:
    store = registry(tmp_path)
    item = OccurrenceInput(
        source_system="LVMS",
        sample_number="S-1",
        analysis_code="CALR-OU",
        ordered_at=datetime(2026, 9, 10, 8, 0),
        source_occurrence_id="WORK-1",
        source_kind="statistics_ordered",
    )

    with pytest.raises(ValueError, match="Radantallet"):
        store.import_batch(
            iter((RegistryImportItem(item),)),
            row_count=2,
            kind="statistics",
            unit_key="hemato",
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 10),
            observed_at=datetime(2026, 9, 10, 10, 0),
            source_fingerprint="synthetic",
        )

    assert store.counts() == (0, 0)
