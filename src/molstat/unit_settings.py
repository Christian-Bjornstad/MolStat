"""Versioned, operator-editable unit definitions; no executable configuration."""
from __future__ import annotations

import codecs
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import os

from ._backlog.config import validate_app_config
from ._statistics.units import Unit, validate_units
from .lvms.report_job import validate_report_job


class UnitConfigError(ValueError):
    pass


def _object(raw, allowed, field):
    if not isinstance(raw, dict):
        raise UnitConfigError(f"{field}: må være et objekt")
    unknown = set(raw) - set(allowed)
    if unknown:
        raise UnitConfigError(f"{field}: ukjente felt: {', '.join(sorted(unknown))}")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UnitConfigError(f"duplikat JSON-nøkkel: {key}")
        result[key] = value
    return result


@dataclass(frozen=True)
class UnitFile:
    unit: Unit
    payload: dict
    digest: str

    @property
    def key(self):
        return self.unit.key

    def legacy_statistics(self):
        return {
            "label": self.unit.label, "profile": self.unit.profile,
            "analysis_codes": list(self.unit.analysis_codes),
            "reports": list(self.payload["statistics"].values()),
        }


def load_unit_file(path: Path, expected_key: str | None = None, *, backlog_path: Path | None = None) -> UnitFile:
    try:
        if path.stat().st_size > 2_000_000:
            raise UnitConfigError("filen er større enn 2 MB")
        raw = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)
        _object(raw, {"schema_version", "key", "label", "profile", "statistics", "backlog"}, "enhet")
        if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
            raise UnitConfigError("schema_version: forventet 1")
        key = raw.get("key")
        if not isinstance(key, str) or (expected_key and key != expected_key):
            raise UnitConfigError("key: filen tilhører en annen enhet")
        if backlog_path is not None:
            if key not in {"hemato", "solide"}:
                raise UnitConfigError("Restansefil støttes bare for Hemato og Solide.")
            raw["backlog"] = load_backlog_file(backlog_path, key)
        if not isinstance(raw.get("label"), str) or not raw["label"].strip():
            raise UnitConfigError("label: navn mangler")
        reports = raw.get("statistics")
        _object(reports, {"workflow", "antall", "resultater", "ekstraksjon", "current", "previous", "production", "macro"}, "statistics")
        expected_roles = {
            "hemato": {"antall", "resultater", "ekstraksjon"},
            "solide": {"antall", "resultater", "ekstraksjon"},
            "flow": {"antall", "resultater"},
            "fish": {"antall", "resultater"},
            "pre": {"resultater"},
            "lege": {"workflow"},
        }.get(raw.get("profile"))
        if expected_roles is None or set(reports) != expected_roles:
            raise UnitConfigError("statistics: rapportrollene stemmer ikke med profilen")
        for name, report in reports.items():
            _object(report, {"job_key", "fetch_report_id", "report_id", "analysis_codes", "comment", "laboratory", "process_codes"}, f"statistics.{name}")
            if not isinstance(report.get("analysis_codes"), list) or (not report["analysis_codes"] and raw.get("profile") != "lege"):
                raise UnitConfigError(f"statistics.{name}.analysis_codes: listen må ha minst én kode")
            if "fetch_report_id" in report and (not isinstance(report["fetch_report_id"], str) or not report["fetch_report_id"].strip()):
                raise UnitConfigError(f"statistics.{name}.fetch_report_id: forventet rapportnavn som tekst")
            if "comment" in report and not isinstance(report["comment"], str):
                raise UnitConfigError(f"statistics.{name}.comment: forventet tekst")
            if raw.get("profile") == "lege" and report.get("job_key") != name:
                raise UnitConfigError(f"statistics.{name}.job_key: må være {name} for denne rapportrollen")
            if raw.get("profile") == "lege":
                storage_stems = {"workflow": "PAT-TID-STOP-SNITT-OU"}
                if report.get("report_id") != storage_stems[name]:
                    raise UnitConfigError(
                        f"statistics.{name}.report_id: patologprofilen krever {storage_stems[name]} som arkivnavn. "
                        "Bruk fetch_report_id for å endre rapporten som hentes fra LVMS."
                    )
        primary = reports.get("antall") or reports.get("resultater") or reports.get("workflow") or reports["current"]
        legacy = {"label": raw["label"], "profile": raw.get("profile"),
                  "analysis_codes": primary["analysis_codes"], "reports": list(reports.values())}
        unit = validate_units({"units": {key: legacy}})[0]
        if len({r.report_id.casefold() for r in unit.reports}) != len(unit.reports):
            raise UnitConfigError("statistics: report_id må være unik for hver rapportrolle")
        for report in unit.reports:
            validate_report_job({"job_key": report.job_key, "report_type": "PRODSTAT", "category": "PATOLOGI",
                                 "report_id": report.fetch_report_id, "analysis_codes": list(report.analysis_codes),
                                 "laboratory": report.laboratory, "process_codes": list(report.process_codes),
                                 "usernames": ["TESTUSER"] if raw.get("profile") == "lege" and report.job_key in {"production", "macro"} else [],
                                 "created_from": "01.01.2024", "created_to": "01.01.2024", "output_stem": report.report_id})
        backlog = raw.get("backlog")
        if backlog is not None:
            _validate_backlog(backlog, key)
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return UnitFile(unit, raw, digest)
    except json.JSONDecodeError as exc:
        raise UnitConfigError(f"CONFIG_SYNTAX: {path.name}, linje {exc.lineno}, kolonne {exc.colno}: kontroller komma, anførselstegn og klammer.") from exc
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, LookupError) as exc:
        raise UnitConfigError(f"CONFIG_INVALID: {path.name}: {exc}") from exc


def _validate_backlog(raw, key):
    _object(raw, {"report", "analyses", "columns"}, "backlog")
    report = raw.get("report")
    _object(report, {"schema_version", "report_type", "category", "report_id", "report_groups", "analysis_codes", "output_stem"}, "backlog.report")
    if not isinstance(report.get("report_groups"), list) or not report["report_groups"]:
        raise UnitConfigError("backlog.report.report_groups: minst én gruppe må angis")
    if type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise UnitConfigError("backlog.report.schema_version: forventet 1")
    job = validate_report_job({**{k: v for k, v in report.items() if k != "schema_version"}, "job_key": "backlog",
                              "created_from": "01.01.2024", "created_to": "01.01.2024"})
    analyses = raw.get("analyses")
    _object(analyses, {"schema_version", "report_id", "unit", "thresholds", "analyses"}, "backlog.analyses")
    if type(analyses.get("schema_version")) is not int or analyses["schema_version"] != 1:
        raise UnitConfigError("backlog.analyses.schema_version: forventet 1")
    _object(analyses.get("unit"), {"key", "label"}, "backlog.analyses.unit")
    _object(analyses.get("thresholds", {}), {"warning_hours", "critical_hours"}, "backlog.thresholds")
    for name, value in analyses.get("thresholds", {}).items():
        if type(value) is not int or value < 1:
            raise UnitConfigError(f"backlog.thresholds.{name}: forventet positivt heltall")
    if not isinstance(analyses.get("analyses"), list):
        raise UnitConfigError("backlog.analyses: forventet analyseliste")
    for index, analysis in enumerate(analyses.get("analyses", [])):
        _object(analysis, {"code", "label", "group", "priority", "enabled", "warning_hours", "critical_hours", "source_codes", "report_group"}, f"backlog.analyses[{index}]")
        for name in ("warning_hours", "critical_hours"):
            if analysis.get(name) is not None and (type(analysis[name]) is not int or analysis[name] < 1):
                raise UnitConfigError(f"backlog.analyses[{index}].{name}: forventet positivt heltall")
    parsed = validate_app_config(analyses)
    used_codes = set()
    for analysis in parsed.analyses:
        if not analysis.enabled:
            continue
        for code in analysis.source_codes or (analysis.code,):
            if code in used_codes:
                raise UnitConfigError("backlog.analyses.source_codes: samme kildekode er koblet til flere aktive analyser")
            used_codes.add(code)
    if parsed.unit.key != key:
        raise UnitConfigError("backlog.analyses.unit.key: feil enhet")
    missing_codes = used_codes - set(job.analysis_codes)
    if missing_codes:
        raise UnitConfigError("backlog.report.analysis_codes: aktive kildekoder mangler: " + ", ".join(sorted(missing_codes)))
    columns = raw.get("columns")
    _object(columns, {"schema_version", "classifier_version", "delimiter", "encoding", "columns", "completed_values"}, "backlog.columns")
    if type(columns.get("schema_version")) is not int or columns["schema_version"] != 1:
        raise UnitConfigError("backlog.columns.schema_version: forventet 1")
    if columns.get("delimiter") not in (",", ";", "\t", "|"):
        raise UnitConfigError("backlog.columns.delimiter: forventet ett skilletegn (, ; tab eller |)")
    codecs.lookup(columns["encoding"])
    if type(columns.get("classifier_version")) is not int or columns["classifier_version"] < 1:
        raise UnitConfigError("backlog.columns.classifier_version: forventet positivt heltall")
    mapping = columns.get("columns")
    allowed = {"sample_id", "occurrence_id", "analysis_code", "material", "collected_at", "arrival_at", "created_at", "analysis_priority", "request_priority", "status", "preliminary_status", "result", "external_comment"}
    _object(mapping, allowed, "backlog.columns.columns")
    if not {"sample_id", "analysis_code", "created_at", "status"} <= set(mapping) or any(not isinstance(v, str) or not v.strip() for v in mapping.values()):
        raise UnitConfigError("backlog.columns.columns: obligatoriske kolonnenavn mangler")
    source_names = [value.strip().casefold() for value in mapping.values()]
    if len(source_names) != len(set(source_names)):
        raise UnitConfigError("backlog.columns.columns: samme kolonnenavn er koblet til flere felt")
    completed = columns.get("completed_values")
    if not isinstance(completed, list) or not completed or any(not isinstance(v, str) or not v.strip() for v in completed):
        raise UnitConfigError("backlog.columns.completed_values: forventet liste med statuser")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_backlog_file(path: Path, key: str) -> dict:
    """One independently editable restanse file per unit, using the same contract."""
    try:
        if path.stat().st_size > 2_000_000:
            raise UnitConfigError("Restansefilen er større enn 2 MB.")
        payload = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)
        _validate_backlog(payload, key)
        return payload
    except (OSError, ValueError, TypeError, LookupError) as exc:
        raise UnitConfigError(f"CONFIG_INVALID: Restansefilen for {key} kunne ikke valideres: {exc}") from exc


def load_active_units(sensitive_root: Path, paths: dict[str, Path], keys, *, backlog_paths: dict[str, Path] | None = None) -> dict[str, UnitFile]:
    result = {}
    for key in keys:
        source = paths.get(key)
        if source is None:
            raise UnitConfigError(f"Enhetsfil (JSON) mangler for {key}. Velg din egen fil i Innstillinger.")
        result[key] = load_unit_file(source, key, backlog_path=(backlog_paths or {}).get(key))
    return result
