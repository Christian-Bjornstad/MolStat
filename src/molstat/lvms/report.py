from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
from typing import Literal, Protocol


ReportKind = Literal["statistics", "backlog"]
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True, slots=True)
class ReportRequest:
    kind: ReportKind
    unit: str
    report_name: str
    date_from: date
    date_to: date

    def __post_init__(self) -> None:
        if self.kind not in ("statistics", "backlog"):
            raise ValueError(f"Ukjent rapporttype: {self.kind}")
        for label, value in (("enhet", self.unit), ("rapport", self.report_name)):
            if not _SAFE_SEGMENT.fullmatch(value):
                raise ValueError(f"Ugyldig {label}: bare filsystemsikre tegn er tillatt.")
        if self.date_from > self.date_to:
            raise ValueError("Fra-dato kan ikke være etter til-dato.")


class LvmsClient(Protocol):
    def fetch(self, request: ReportRequest, download_dir: Path) -> Path: ...

