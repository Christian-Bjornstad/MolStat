"""Identifikatorfri presentasjonsmodell for nettlesertavla."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from statistics import median
from typing import Sequence

from .config import AppConfig
from .domain import Sample, WorkflowStage


class Severity(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    OVERDUE = "OVERDUE"
    EMPTY = "EMPTY"


@dataclass(frozen=True)
class AnalysisDashboard:
    analysis_code: str
    label: str
    severity: Severity
    ready: int
    awaiting_approval: int
    in_transit: int
    overdue: int
    median_ready_hours: float | None
    oldest_ready_hours: float | None

    def to_public_dict(self) -> dict[str, object]:
        return {
            "analysisCode": self.analysis_code,
            "label": self.label,
            "severity": self.severity.value,
            "ready": self.ready,
            "awaitingApproval": self.awaiting_approval,
            "inTransit": self.in_transit,
            "overdue": self.overdue,
            "medianReadyHours": self.median_ready_hours,
            "oldestReadyHours": self.oldest_ready_hours,
        }


@dataclass(frozen=True)
class DashboardSnapshot:
    generated_at: datetime
    unit_label: str
    is_stale: bool
    analyses: tuple[AnalysisDashboard, ...]
    empty_analysis_count: int

    @property
    def totals(self) -> dict[str, int]:
        return {
            "ready": sum(item.ready for item in self.analyses),
            "awaitingApproval": sum(item.awaiting_approval for item in self.analyses),
            "inTransit": sum(item.in_transit for item in self.analyses),
            "overdue": sum(item.overdue for item in self.analyses),
        }

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "generatedAt": self.generated_at.isoformat(),
            "unitLabel": self.unit_label,
            "isStale": self.is_stale,
            "totals": self.totals,
            "emptyAnalysisCount": self.empty_analysis_count,
            "analyses": [item.to_public_dict() for item in self.analyses],
        }


def _ready_age(sample: Sample, generated_at: datetime) -> float:
    reference = sample.arrived_at or sample.ordered_at
    return max(0.0, (generated_at - reference).total_seconds() / 3600.0)


def build_dashboard_snapshot(
    config: AppConfig,
    samples: Sequence[Sample],
    generated_at: datetime,
    stale_after: timedelta,
    *,
    source_updated_at: datetime | None = None,
) -> DashboardSnapshot:
    dashboards: list[tuple[int, AnalysisDashboard]] = []
    empty_analysis_count = 0
    severity_rank = {
        Severity.OVERDUE: 0,
        Severity.WARNING: 1,
        Severity.NORMAL: 2,
        Severity.EMPTY: 3,
    }

    for index, analysis in enumerate(config.analyses):
        if not analysis.enabled:
            continue
        selected = [item for item in samples if item.analysis_code == analysis.code]
        ready_samples = [item for item in selected if item.stage is WorkflowStage.READY]
        awaiting = sum(
            item.stage is WorkflowStage.AWAITING_APPROVAL for item in selected
        )
        in_transit = sum(item.stage is WorkflowStage.IN_TRANSIT for item in selected)
        if not ready_samples and not awaiting and not in_transit:
            empty_analysis_count += 1
            continue

        ages = [_ready_age(item, generated_at) for item in ready_samples]
        critical = analysis.effective_critical(config.thresholds)
        warning = analysis.effective_warning(config.thresholds)
        overdue = sum(age >= critical for age in ages)
        oldest = max(ages) if ages else None
        if overdue:
            severity = Severity.OVERDUE
        elif oldest is not None and oldest >= warning:
            severity = Severity.WARNING
        else:
            severity = Severity.NORMAL
        dashboard = AnalysisDashboard(
            analysis_code=analysis.code,
            label=analysis.label,
            severity=severity,
            ready=len(ready_samples),
            awaiting_approval=awaiting,
            in_transit=in_transit,
            overdue=overdue,
            median_ready_hours=median(ages) if ages else None,
            oldest_ready_hours=oldest,
        )
        dashboards.append((index, dashboard))

    dashboards.sort(key=lambda item: (severity_rank[item[1].severity], item[0]))
    source_time = source_updated_at or generated_at
    return DashboardSnapshot(
        generated_at=generated_at,
        unit_label=config.unit.label,
        is_stale=generated_at - source_time > stale_after,
        analyses=tuple(item for _, item in dashboards),
        empty_analysis_count=empty_analysis_count,
    )
