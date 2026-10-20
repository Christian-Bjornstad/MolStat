"""Domenemodell for klassifiserte restanseprøver."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class WorkflowStage(str, Enum):
    """Operativt stadium for en rad i restanserapporten."""

    READY = "ready"
    AWAITING_APPROVAL = "awaiting_approval"
    IN_TRANSIT = "in_transit"


@dataclass(frozen=True)
class Sample:
    """Én klassifisert prøve fra RESTANSE-rapporten."""

    sample_id: str
    analysis_code: str
    ordered_at: datetime
    arrived_at: datetime | None
    stage: WorkflowStage

    @property
    def age_anchor(self) -> datetime | None:
        return self.arrived_at if self.stage is WorkflowStage.READY else None


@dataclass(frozen=True)
class BacklogDetail:
    """Én restanseanalyse før den pseudonyme eksporten bygges.

    ``sample_id`` brukes kun til intern deduplisering og skjules fra repr/logg.
    Råverdien lagres aldri i detaljhistorikken; den erstattes med MolStat-ID.
    """

    sample_id: str = field(repr=False)
    analysis_code: str
    analysis_group: str
    material: str
    collected_at: datetime | None
    arrived_at: datetime | None
    ordered_at: datetime
    analysis_priority: str
    request_priority: str
    analysis_status: str
    preliminary_status: str
    stage: WorkflowStage
    analysis_result: str
    external_analysis_comment: str
    source_occurrence_id: str = field(default="", repr=False)


def parse_lvms_datetime(text: str) -> datetime:
    """Parse LVMS dato/tid-streng (DD.MM.YYYY HH:MM eller DD.MM.YYYY)."""
    text = text.strip()
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"ugyldig datoformat: {text!r}")
