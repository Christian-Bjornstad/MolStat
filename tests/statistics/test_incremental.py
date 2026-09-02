from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from molstat.statistics import (
    IncrementalPlanError,
    plan_all_units,
    plan_unit,
)
from molstat.statistics import ManifestStore, RunRecord
from molstat.statistics import load_units


def write_units(tmp_path: Path) -> Path:
    raw = {
        "units": {
            "hemato": {
                "label": "Hemato",
                "analysis_codes": ["JAK2-V617F-OU", "CALR-OU"],
                "reports": [
                    {"job_key": "ordered", "report_id": "PAT-DIT-ANTALL-OU"},
                    {
                        "job_key": "answered",
                        "report_id": "PAT-DIT-RESULTATER-OU",
                    },
                ],
            },
            "solide": {
                "analysis_codes": ["EKSTRAKSJON-SO-OU"],
                "reports": [
                    {"job_key": "ordered", "report_id": "PAT-DIT-ANTALL-SO"},
                ]
            },
        }
    }
    path = tmp_path / "units.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def seed_history(
    statistics: Path, unit: str, report_id: str, last_to: date
) -> None:
    store = ManifestStore(statistics / "manifest.sqlite")
    store.record_run(
        RunRecord(
            unit=unit,
            job_key="ordered",
            report_id=report_id,
            created_from=last_to - timedelta(days=6),
            created_to=last_to,
            filename=f"{report_id}__{last_to.isoformat()}__{last_to.isoformat()}.csv",
        )
    )


def test_plan_unit_builds_fetches_with_overlap(tmp_path: Path) -> None:
    units = load_units(write_units(tmp_path))
    statistics = tmp_path / "K"
    today = date(2026, 8, 22)
    seed_history(statistics, "hemato", "PAT-DIT-ANTALL-OU", date(2026, 8, 19))
    seed_history(
        statistics, "hemato", "PAT-DIT-RESULTATER-OU", date(2026, 8, 19)
    )
    plan = plan_unit(units[0], statistics_root=statistics, today=today)
    assert len(plan.fetches) == 2
    fetch = plan.fetches[0]
    assert fetch.created_from == date(2026, 8, 17)
    assert fetch.created_to == today


def test_plan_unit_marks_up_to_date(tmp_path: Path) -> None:
    units = load_units(write_units(tmp_path))
    statistics = tmp_path / "K"
    today = date(2026, 8, 22)
    seed_history(
        statistics, "hemato", "PAT-DIT-ANTALL-OU", date(2026, 8, 22)
    )
    seed_history(
        statistics, "hemato", "PAT-DIT-RESULTATER-OU", date(2026, 8, 22)
    )
    plan = plan_unit(units[0], statistics_root=statistics, today=today)
    assert plan.fetches == ()
    assert plan.up_to_date == (
        "PAT-DIT-ANTALL-OU",
        "PAT-DIT-RESULTATER-OU",
    )


def test_plan_unit_first_run_fetches_from_default_backfill(
    tmp_path: Path,
) -> None:
    units = load_units(write_units(tmp_path))
    today = date(2026, 8, 22)
    plan = plan_unit(
        units[0], statistics_root=tmp_path / "K", today=today
    )
    assert len(plan.fetches) == 2
    assert all(fetch.created_from == date(2024, 1, 1) for fetch in plan.fetches)
    assert all(fetch.created_to == today for fetch in plan.fetches)


def test_plan_all_units_covers_every_unit(tmp_path: Path) -> None:
    units_path = write_units(tmp_path)
    statistics = tmp_path / "K"
    today = date(2026, 8, 22)
    for unit_key, report_id in (
        ("hemato", "PAT-DIT-ANTALL-OU"),
        ("hemato", "PAT-DIT-RESULTATER-OU"),
        ("solide", "PAT-DIT-ANTALL-SO"),
    ):
        seed_history(statistics, unit_key, report_id, date(2026, 8, 20))
    plans = plan_all_units(
        units_path=units_path, statistics_root=statistics, today=today
    )
    assert [plan.unit.key for plan in plans] == ["hemato", "solide"]
    assert sum(len(plan.fetches) for plan in plans) == 3


def test_plan_all_units_rejects_everything_up_to_date(tmp_path: Path) -> None:
    units_path = write_units(tmp_path)
    statistics = tmp_path / "K"
    today = date(2026, 8, 22)
    for unit_key, report_id in (
        ("hemato", "PAT-DIT-ANTALL-OU"),
        ("hemato", "PAT-DIT-RESULTATER-OU"),
        ("solide", "PAT-DIT-ANTALL-SO"),
    ):
        seed_history(statistics, unit_key, report_id, today)
    with pytest.raises(IncrementalPlanError, match="oppdatert"):
        plan_all_units(
            units_path=units_path, statistics_root=statistics, today=today
        )


def test_plan_all_units_missing_units_file(tmp_path: Path) -> None:
    with pytest.raises(IncrementalPlanError):
        plan_all_units(
            units_path=tmp_path / "missing.json",
            statistics_root=tmp_path / "K",
            today=date(2026, 8, 22),
        )

