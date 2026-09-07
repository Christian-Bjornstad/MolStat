"""Identifier-free hourly aggregate history for Power BI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .config import AppConfig
from .dashboard import Severity, aggregate_analyses
from .domain import Sample


@dataclass(frozen=True, slots=True)
class BacklogHistoryRow:
    observed_at: datetime
    unit_key: str
    analysis_code: str
    analysis_label: str
    ready_count: int
    awaiting_approval_count: int
    in_transit_count: int
    overdue_count: int
    median_ready_hours: float | None
    oldest_ready_hours: float | None
    severity: Severity
    invalid_rows: int
    excluded_rows: int
    source_is_fresh: bool
    classifier_version: int


def hour_slot(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def build_history_rows(
    config: AppConfig,
    samples: Sequence[Sample],
    observed_at: datetime,
    *,
    invalid_rows: int,
    excluded_rows: int,
    classifier_version: int,
) -> tuple[BacklogHistoryRow, ...]:
    slot = hour_slot(observed_at)
    return tuple(
        BacklogHistoryRow(
            observed_at=slot,
            unit_key=config.unit.key,
            analysis_code=analysis.analysis_code,
            analysis_label=analysis.label,
            ready_count=analysis.ready,
            awaiting_approval_count=analysis.awaiting_approval,
            in_transit_count=analysis.in_transit,
            overdue_count=analysis.overdue,
            median_ready_hours=analysis.median_ready_hours,
            oldest_ready_hours=analysis.oldest_ready_hours,
            severity=analysis.severity,
            invalid_rows=invalid_rows,
            excluded_rows=excluded_rows,
            source_is_fresh=True,
            classifier_version=classifier_version,
        )
        for analysis in aggregate_analyses(config, samples, observed_at)
    )
