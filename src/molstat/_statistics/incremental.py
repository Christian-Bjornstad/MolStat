"""Incremental fetch orchestration.

Combines the manifest, the units configuration and the job templates to
answer: which reports need fetching, for which interval, right now?
This module never contacts LVMS; the GUI or a scheduled run calls it
before handing the resulting jobs to the batch runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from molstat._statistics.manifest import (
    DEFAULT_BACKFILL_FROM,
    ManifestStore,
    UnitReport as ManifestUnitReport,
    plan_incremental_interval,
)
from molstat._statistics.units import Unit, UnitReport, load_units
from molstat._statistics.units import UnitsConfigError


class IncrementalPlanError(ValueError):
    """The incremental fetch plan could not be produced."""


@dataclass(frozen=True)
class PlannedFetch:
    """One report to fetch in the next run."""

    unit: Unit
    report: UnitReport
    created_from: date
    created_to: date


@dataclass(frozen=True)
class IncrementalPlan:
    """Everything the next run should fetch, per unit."""

    unit: Unit
    fetches: tuple[PlannedFetch, ...]
    up_to_date: tuple[str, ...]


def plan_unit(
    unit: Unit,
    *,
    statistics_root: Path,
    today: date,
    overlap_days: int = 3,
) -> IncrementalPlan:
    """Plan the next incremental fetch for one unit.

    Reports whose manifest history already reaches today are marked
    up to date and skipped. Reports without any history get their first
    window from DEFAULT_BACKFILL_FROM (01.01.2024) to today.
    """
    store = ManifestStore(statistics_root / "manifest.sqlite")
    fetches: list[PlannedFetch] = []
    up_to_date: list[str] = []
    for report in unit.reports:
        last = store.last_completed_to(unit.key, report.report_id)
        if last is None:
            fetches.append(
                PlannedFetch(
                    unit=unit,
                    report=report,
                    created_from=DEFAULT_BACKFILL_FROM,
                    created_to=today,
                )
            )
            continue
        if last >= today:
            up_to_date.append(report.report_id)
            continue
        start, end = plan_incremental_interval(
            ManifestUnitReport(
                unit=unit.key,
                job_key=report.job_key,
                report_id=report.report_id,
            ),
            last_completed_to=last,
            today=today,
            overlap_days=overlap_days,
        )
        fetches.append(
            PlannedFetch(
                unit=unit,
                report=report,
                created_from=start,
                created_to=end,
            )
        )
    return IncrementalPlan(
        unit=unit,
        fetches=tuple(fetches),
        up_to_date=tuple(up_to_date),
    )


def plan_all_units(
    *,
    units_path: Path,
    statistics_root: Path,
    today: date,
    overlap_days: int = 3,
) -> tuple[IncrementalPlan, ...]:
    """Plan the next incremental fetch for every configured unit."""
    try:
        units = load_units(units_path)
    except UnitsConfigError as exc:
        raise IncrementalPlanError(str(exc)) from exc
    plans = tuple(
        plan_unit(
            unit,
            statistics_root=statistics_root,
            today=today,
            overlap_days=overlap_days,
        )
        for unit in units
    )
    if not any(plan.fetches for plan in plans):
        raise IncrementalPlanError("alle rapporter er oppdatert")
    return plans

