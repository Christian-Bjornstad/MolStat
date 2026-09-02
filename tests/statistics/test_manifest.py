from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from molstat.statistics import (
    ManifestError,
    ManifestStore,
    RunRecord,
    UnitReport,
    load_statistics_settings,
    plan_incremental_interval,
)


def make_record(filename: str = "PAT-DIT-ANTALL-OU__2026-08-01__2026-08-07.csv") -> RunRecord:
    return RunRecord(
        unit="hemato",
        job_key="ordered",
        report_id="PAT-DIT-ANTALL-OU",
        created_from=date(2026, 8, 1),
        created_to=date(2026, 8, 7),
        filename=filename,
    )


def write_settings(tmp_path: Path) -> Path:
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{"statistics_root": "K:\\\\Statistikk"}', encoding="utf-8"
    )
    return settings


def test_record_and_read_last_completed_to(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path / "manifest.sqlite")
    assert store.last_completed_to("hemato", "PAT-DIT-ANTALL-OU") is None
    store.record_run(make_record())
    assert store.last_completed_to(
        "hemato", "PAT-DIT-ANTALL-OU"
    ) == date(2026, 8, 7)


def test_duplicate_filename_is_rejected(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path / "manifest.sqlite")
    store.record_run(make_record())
    with pytest.raises(ManifestError):
        store.record_run(make_record())


def test_same_filename_other_unit_is_allowed(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path / "manifest.sqlite")
    record = make_record()
    other = RunRecord(
        unit="solide",
        job_key=record.job_key,
        report_id=record.report_id,
        created_from=record.created_from,
        created_to=record.created_to,
        filename=record.filename,
    )
    store.record_run(record)
    store.record_run(other)
    assert store.has_filename("solide", record.filename)
    assert not store.has_filename("hemato", "missing.csv")


def test_invalid_interval_is_rejected() -> None:
    with pytest.raises(ManifestError):
        RunRecord(
            unit="hemato",
            job_key="ordered",
            report_id="R",
            created_from=date(2026, 8, 7),
            created_to=date(2026, 8, 1),
            filename="x.csv",
        )


def test_invalid_unit_is_rejected(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path / "manifest.sqlite")
    with pytest.raises(ManifestError):
        store.record_run(
            RunRecord(
                unit="ikke gyldig!",
                job_key="ordered",
                report_id="R",
                created_from=date(2026, 1, 1),
                created_to=date(2026, 1, 2),
                filename="x.csv",
            )
        )


def test_plan_first_run_without_history_starts_at_backfill_from() -> None:
    start, end = plan_incremental_interval(
        UnitReport("hemato", "ordered", "PAT-DIT-ANTALL-OU"),
        last_completed_to=None,
        today=date(2026, 8, 22),
    )
    assert start == date(2024, 1, 1)
    assert end == date(2026, 8, 22)


def test_plan_continues_after_last_completed_with_overlap() -> None:
    start, end = plan_incremental_interval(
        UnitReport("hemato", "ordered", "PAT-DIT-ANTALL-OU"),
        last_completed_to=date(2026, 8, 20),
        today=date(2026, 8, 22),
    )
    assert start == date(2026, 8, 18)
    assert end == date(2026, 8, 22)


def test_plan_refuses_gap_over_thirty_days() -> None:
    with pytest.raises(ManifestError, match="30 days"):
        plan_incremental_interval(
            UnitReport("hemato", "ordered", "PAT-DIT-ANTALL-OU"),
            last_completed_to=date(2026, 5, 1),
            today=date(2026, 8, 22),
        )


def test_settings_load_and_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = load_statistics_settings(write_settings(tmp_path))
    assert root == Path("K:/Statistikk").resolve()
    monkeypatch.setenv("LVMS_STATISTICS_ROOT", "D:/Annet")
    root = load_statistics_settings(write_settings(tmp_path))
    assert root == Path("D:/Annet").resolve()


def test_settings_missing_key_is_rejected(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_statistics_settings(settings)

