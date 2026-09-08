"""Hourly aggregate and identifier-free detail history for Prøveflyt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from .config import AppConfig
from .dashboard import Severity, aggregate_analyses
from .domain import BacklogDetail, Sample


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


@dataclass(frozen=True, slots=True)
class BacklogDetailHistoryRow:
    observed_at: datetime
    unit_key: str
    material: str
    analysis_code: str
    nucleic_acid: str
    report_group: str
    analysis_group_code: str
    analysis_group_label: str
    collected_at: datetime | None
    arrived_at: datetime | None
    ordered_at: datetime
    analysis_priority: str
    request_priority: str
    analysis_status: str
    preliminary_status: str
    workflow_stage: str
    response_deadline: str
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


def build_detail_history_rows(
    config: AppConfig,
    details: Sequence[BacklogDetail],
    observed_at: datetime,
    *,
    analysis_lookup: Mapping[str, Mapping[str, str]],
    classifier_version: int,
) -> tuple[BacklogDetailHistoryRow, ...]:
    """Bygg detaljsnapshot uten å føre prøveidentifikator over grensen."""
    slot = hour_slot(observed_at)
    rows: list[BacklogDetailHistoryRow] = []
    for detail in details:
        configured = config.analysis_by_code(detail.analysis_group)
        metadata = analysis_lookup.get(detail.analysis_code, {})
        rows.append(
            BacklogDetailHistoryRow(
                observed_at=slot,
                unit_key=config.unit.key,
                material=detail.material,
                analysis_code=detail.analysis_code,
                nucleic_acid=str(metadata.get("Nukleinsyre", "")),
                report_group=str(metadata.get("Rapportgruppe", "")),
                analysis_group_code=detail.analysis_group,
                analysis_group_label=(
                    configured.label if configured is not None else detail.analysis_group
                ),
                collected_at=detail.collected_at,
                arrived_at=detail.arrived_at,
                ordered_at=detail.ordered_at,
                analysis_priority=detail.analysis_priority,
                request_priority=detail.request_priority,
                analysis_status=detail.analysis_status,
                preliminary_status=detail.preliminary_status,
                workflow_stage=detail.stage.value,
                response_deadline=str(metadata.get("Svarfrist", "")),
                classifier_version=classifier_version,
            )
        )
    return tuple(rows)
