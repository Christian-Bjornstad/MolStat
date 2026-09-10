from datetime import datetime
from pathlib import Path

from molstat.excel_search import read_excel_snapshot

from .helpers import populated_database


def test_read_model_reconciles_samples_occurrences_and_current_backlog(
    tmp_path: Path,
) -> None:
    database = populated_database(tmp_path / "molstat.sqlite3")

    snapshot = read_excel_snapshot(
        database,
        generated_at=datetime(2026, 9, 10, 12, 30),
    )

    assert len(snapshot.samples) == 1
    assert len(snapshot.analyses) == 2
    assert snapshot.samples[0].sample_number == "00123456789012345678"
    assert snapshot.samples[0].occurrence_count == 2
    assert snapshot.samples[0].backlog_count == 1
    assert [row.in_backlog for row in snapshot.analyses] == [False, True]
    assert snapshot.analyses[0].approved_at == datetime(2026, 9, 9, 10, 0)
