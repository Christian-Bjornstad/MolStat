"""Eksplisitt adapter fra PAT-DIT-RESTANSE-OU CSV til domenemodellen."""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .domain import Sample, WorkflowStage, parse_lvms_datetime


class CsvImportError(ValueError):
    pass


# Resultater som betyr at prøven er ferdig godkjent og ikke skal vises på tavla.
_FINALISED_MARKERS = ("utført", "utfort", "markør", "etablert")
# Markører for at en prøve er stoppet uten å bli godkjent
# (skal telles som "Ikke godkjent" / Awaiting approval).
_NOT_PERFORMED_MARKERS = ("ikke utført", "ikke utfort", "ikke utført.")


def classify_workflow(
    status_text: str,
    arrival_text: str,
    result_text: str,
    external_comment: str,
    completed_values: tuple[str, ...],
) -> WorkflowStage | None:
    """Bestem arbeidsflytstadium for én CSV-rad.

    Returnerer None når raden ikke skal telles på tavla
    (fordi den er ferdig godkjent, ikke bare stoppet).
    """
    result_cf = (result_text or "").casefold()
    comment_cf = (external_comment or "").casefold()

    # "Ikke utført" i resultat eller kommentar = stoppet, telles som ikke-godkjent.
    # NB: må sjekkes FØR ferdig-markører fordi "ikke utført" inneholder "utført".
    if any(marker in result_cf for marker in _NOT_PERFORMED_MARKERS):
        return WorkflowStage.AWAITING_APPROVAL
    if any(marker in comment_cf for marker in _NOT_PERFORMED_MARKERS):
        return WorkflowStage.AWAITING_APPROVAL

    # Ferdige, godkjente resultater telles ikke.
    if any(marker in result_cf for marker in _FINALISED_MARKERS):
        return None
    if any(marker in comment_cf for marker in _FINALISED_MARKERS):
        return None

    status_norm = status_text.strip().casefold()
    completed = {value.casefold() for value in completed_values}
    arrival_cf = (arrival_text or "").casefold()
    if status_norm in completed:
        return WorkflowStage.AWAITING_APPROVAL

    # Status er "Initial" / pending. Trenger ankomst for å være klar.
    if arrival_cf in {"", "na", "n/a"}:
        return WorkflowStage.IN_TRANSIT
    try:
        parse_lvms_datetime(arrival_text)
    except ValueError:
        return WorkflowStage.IN_TRANSIT
    return WorkflowStage.READY


@dataclass(frozen=True)
class CsvContract:
    delimiter: str
    encoding: str
    columns: dict[str, str]
    completed_values: tuple[str, ...]
    classifier_version: int = 2


@dataclass(frozen=True)
class CsvImportResult:
    samples: tuple[Sample, ...]
    rows_read: int
    duplicate_rows: int
    invalid_rows: int
    excluded_rows: int
    fingerprint: str


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unwrap_lvms_text(value: object) -> str:
    """Strip LVMS' Excel-friendly =T("...") wrapper."""
    text = str(value or "").strip()
    if text.startswith('=T("') and text.endswith('")'):
        return text[4:-2].replace('""', '"')
    return text


def _optional_value(row: dict, contract: CsvContract, key: str) -> str:
    column = contract.columns.get(key)
    if not column:
        return ""
    return _unwrap_lvms_text(row.get(column))


def read_restanse_csv(
    path: Path,
    contract: CsvContract,
    *,
    analysis_groups: dict[str, tuple[str, ...]] | None = None,
) -> CsvImportResult:
    path = Path(path)
    required_keys = ("sample_id", "analysis_code", "created_at", "status")
    missing_mapping = [key for key in required_keys if key not in contract.columns]
    if missing_mapping:
        raise CsvImportError("kolonnekontrakten mangler: " + ", ".join(missing_mapping))

    try:
        stream = path.open("r", encoding=contract.encoding, newline="")
    except OSError as exc:
        raise CsvImportError(f"kunne ikke lese CSV: {exc}") from exc

    group_by_code = {
        code: group
        for group, codes in (analysis_groups or {}).items()
        for code in codes
    }
    samples_by_key: dict[tuple[str, str], Sample] = {}
    rows_read = duplicate_rows = invalid_rows = excluded_rows = 0
    with stream:
        reader = csv.DictReader(stream, delimiter=contract.delimiter)
        fieldnames = set(reader.fieldnames or ())
        expected = {contract.columns[key] for key in required_keys}
        missing = sorted(expected - fieldnames)
        if missing:
            raise CsvImportError("CSV mangler kolonner: " + ", ".join(missing))

        for row in reader:
            def has_content(value: object) -> bool:
                if isinstance(value, list):
                    return any(str(part).strip() for part in value)
                return bool(str(value or "").strip())

            if not any(has_content(value) for value in row.values()):
                continue
            rows_read += 1
            try:
                sample_id = _unwrap_lvms_text(row[contract.columns["sample_id"]])
                analysis_code = _unwrap_lvms_text(row[contract.columns["analysis_code"]])
                analysis_code = group_by_code.get(analysis_code, analysis_code)
                created_text = _unwrap_lvms_text(row[contract.columns["created_at"]])
                status_text = _unwrap_lvms_text(row[contract.columns["status"]])
                preliminary_text = _optional_value(row, contract, "preliminary_status")
                result_text = _optional_value(row, contract, "result")
                external_comment = _optional_value(row, contract, "external_comment")
                arrival_text = _optional_value(row, contract, "arrival_at")
                workflow_arrival = arrival_text or created_text
                stage = classify_workflow(
                    status_text,
                    workflow_arrival,
                    result_text,
                    external_comment,
                    contract.completed_values,
                )
                if stage is None:
                    excluded_rows += 1
                    continue
                if created_text.casefold() in {"", "na", "n/a"}:
                    excluded_rows += 1
                    continue
                if not sample_id or not analysis_code:
                    raise ValueError("obligatorisk felt er tomt")
                status_completed = status_text.strip().casefold() in {
                    value.casefold() for value in contract.completed_values
                }
                not_performed = any(
                    marker in (result_text + " " + external_comment).casefold()
                    for marker in _NOT_PERFORMED_MARKERS
                )
                if (
                    status_completed
                    and "preliminary_status" in contract.columns
                    and preliminary_text.casefold() in {"", "initial"}
                    and not not_performed
                ):
                    excluded_rows += 1
                    continue
                sample = Sample(
                    sample_id=sample_id,
                    analysis_code=analysis_code,
                    ordered_at=parse_lvms_datetime(created_text),
                    arrived_at=(
                        parse_lvms_datetime(arrival_text)
                        if arrival_text.casefold() not in {"", "na", "n/a"}
                        else None
                    ),
                    stage=stage,
                )
            except (KeyError, ValueError, TypeError):
                invalid_rows += 1
                continue
            key = (sample.sample_id, sample.analysis_code)
            if key in samples_by_key:
                duplicate_rows += 1
            samples_by_key[key] = sample

    return CsvImportResult(
        samples=tuple(samples_by_key.values()), rows_read=rows_read,
        duplicate_rows=duplicate_rows, invalid_rows=invalid_rows,
        excluded_rows=excluded_rows,
        fingerprint=file_fingerprint(path),
    )
