from pathlib import Path

from molstat.statistics import _report_archives


def test_corrected_export_replaces_same_interval_without_deleting_history(tmp_path):
    for suffix in ("", "__r2", "__r9", "__r10"):
        (tmp_path / f"REPORT__2026-10-01__2026-10-07{suffix}.csv").write_text("rows")
    previous = tmp_path / "REPORT__2026-09-01__2026-09-30.csv"
    previous.write_text("previous interval")
    current = tmp_path / "REPORT__2026-10-01__2026-10-07__r10.csv"

    selected = _report_archives(current)

    assert selected == (previous, current)
    assert len(list(tmp_path.glob("*.csv"))) == 5


def test_unrelated_report_prefix_is_excluded(tmp_path):
    source = tmp_path / "REPORT__2026-10-01__2026-10-07.csv"
    source.write_text("rows")
    (tmp_path / "REPORT_OTHER__2026-10-01__2026-10-07.csv").write_text("other")
    assert _report_archives(source) == (source,)
