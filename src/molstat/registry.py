"""Sensitive sample identity and registry contracts.

Only opaque hashes are used as cross-report occurrence keys. Human-readable
sample numbers remain inside the protected database and must never be logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path


class IdentityContractError(ValueError):
    """Raised when the versioned LVMS identity contract is invalid."""


@dataclass(frozen=True, slots=True)
class ReportIdentityContract:
    sample_id_columns: tuple[str, ...]
    occurrence_id_columns: tuple[str, ...]
    analysis_code_columns: tuple[str, ...]
    ordered_at_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IdentityContract:
    source_system: str
    sample_number_scope: str
    reports: dict[str, ReportIdentityContract]


@dataclass(frozen=True, slots=True)
class OccurrenceIdentity:
    key: str
    uses_fallback: bool


def normalize_identifier(value: object) -> str:
    """Normalize an LVMS identifier without interpreting it as a number."""

    text = str(value or "").strip()
    if text.startswith('=T("') and text.endswith('")'):
        text = text[4:-2].replace('""', '"').strip()
    return text.upper()


def build_occurrence_identity(
    *,
    source_system: str,
    sample_number: str,
    analysis_code: str,
    ordered_at: datetime,
    source_occurrence_id: str | None = None,
) -> OccurrenceIdentity:
    """Build a stable opaque key from immutable source identity fields."""

    source = normalize_identifier(source_system)
    occurrence = normalize_identifier(source_occurrence_id)
    if occurrence:
        parts = ("source-id", source, occurrence)
        uses_fallback = False
    else:
        sample = normalize_identifier(sample_number)
        analysis = normalize_identifier(analysis_code)
        if not source or not sample or not analysis:
            raise ValueError("Identitetsfeltene kan ikke være tomme.")
        parts = (
            "fallback",
            source,
            sample,
            analysis,
            ordered_at.isoformat(timespec="seconds"),
        )
        uses_fallback = True
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return OccurrenceIdentity(digest.hexdigest(), uses_fallback)


def load_identity_contract(path: Path) -> IdentityContract:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityContractError("Kunne ikke lese identitetskontrakten.") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise IdentityContractError("Ukjent identitetskontrakt.")
    source_system = _required_text(raw, "source_system")
    scope = _required_text(raw, "sample_number_scope")
    reports_raw = raw.get("reports")
    if not isinstance(reports_raw, dict) or not reports_raw:
        raise IdentityContractError("Identitetskontrakten mangler rapporter.")
    reports: dict[str, ReportIdentityContract] = {}
    for name, report_raw in reports_raw.items():
        if not isinstance(name, str) or not isinstance(report_raw, dict):
            raise IdentityContractError("Ugyldig rapport i identitetskontrakten.")
        reports[name] = ReportIdentityContract(
            sample_id_columns=_text_list(report_raw, "sample_id_columns"),
            occurrence_id_columns=_text_list(report_raw, "occurrence_id_columns"),
            analysis_code_columns=_text_list(report_raw, "analysis_code_columns"),
            ordered_at_columns=_text_list(report_raw, "ordered_at_columns"),
        )
    return IdentityContract(source_system, scope, reports)


def _required_text(raw: dict, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IdentityContractError(f"Identitetskontrakten mangler {key}.")
    return value.strip()


def _text_list(raw: dict, key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise IdentityContractError(f"Identitetskontrakten har ugyldig {key}.")
    result = tuple(item.strip() for item in value)
    if len(set(result)) != len(result):
        raise IdentityContractError(f"Identitetskontrakten har duplikater i {key}.")
    return result
