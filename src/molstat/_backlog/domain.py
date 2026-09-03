"""Domenemodell for klassifiserte restanseprøver."""

from __future__ import annotations

from dataclasses import dataclass
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


def parse_lvms_datetime(text: str) -> datetime:
    """Parse LVMS dato/tid-streng (DD.MM.YYYY HH:MM eller DD.MM.YYYY)."""
    text = text.strip()
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"ugyldig datoformat: {text!r}")
