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


def default_unit_file(key: str) -> Path:
    if key not in ("hemato", "solide", "flow", "fish", "pre", "lege"):
        raise UnitConfigError("Enheten trenger en importert definisjon.")
    return Path(__file__).parent / "defaults" / "units" / f"{key}.json"


def load_unit_file(path: Path, expected_key: str | None = None) -> UnitFile:
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
        if not isinstance(raw.get("label"), str) or not raw["label"].strip():
            raise UnitConfigError("label: navn mangler")
        reports = raw.get("statistics")
        _object(reports, {"antall", "resultater", "ekstraksjon", "current", "previous"}, "statistics")
        expected_roles = {
            "hemato": {"antall", "resultater", "ekstraksjon"},
            "solide": {"antall", "resultater", "ekstraksjon"},
            "flow": {"antall", "resultater"},
            "fish": {"antall", "resultater"},
            "pre": {"resultater"},
            "lege": {"current", "previous"},
        }.get(raw.get("profile"))
        if expected_roles is None or set(reports) != expected_roles:
            raise UnitConfigError("statistics: rapportrollene stemmer ikke med profilen")
        for name, report in reports.items():
            _object(report, {"job_key", "fetch_report_id", "report_id", "analysis_codes", "comment"}, f"statistics.{name}")
            if not isinstance(report.get("analysis_codes"), list) or (not report["analysis_codes"] and raw.get("profile") != "lege"):
                raise UnitConfigError(f"statistics.{name}.analysis_codes: listen må ha minst én kode")
        primary = reports.get("antall") or reports.get("resultater") or reports["current"]
        legacy = {"label": raw["label"], "profile": raw.get("profile"),
                  "analysis_codes": primary["analysis_codes"], "reports": list(reports.values())}
        unit = validate_units({"units": {key: legacy}})[0]
        if len({r.report_id.casefold() for r in unit.reports}) != len(unit.reports):
            raise UnitConfigError("statistics: report_id må være unik for hver rapportrolle")
        for report in unit.reports:
            validate_report_job({"job_key": report.job_key, "report_type": "PRODSTAT", "category": "PATOLOGI",
                                 "report_id": report.fetch_report_id, "analysis_codes": list(report.analysis_codes),
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
    validate_report_job({**{k: v for k, v in report.items() if k != "schema_version"}, "job_key": "backlog",
                         "created_from": "01.01.2024", "created_to": "01.01.2024"})
    analyses = raw.get("analyses")
    _object(analyses, {"schema_version", "report_id", "unit", "thresholds", "analyses"}, "backlog.analyses")
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
    columns = raw.get("columns")
    _object(columns, {"schema_version", "classifier_version", "delimiter", "encoding", "columns", "completed_values"}, "backlog.columns")
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
    completed = columns.get("completed_values")
    if not isinstance(completed, list) or not completed or any(not isinstance(v, str) or not v.strip() for v in completed):
        raise UnitConfigError("backlog.columns.completed_values: forventet liste med statuser")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def activate_unit_file(source: Path, config_root: Path, key: str) -> Path:
    candidate = load_unit_file(source, key)
    destination = config_root / "units" / f"{candidate.key}.json"
    if destination.is_file():
        previous = load_unit_file(destination, key)
        write_json(config_root / "revisions" / previous.digest / f"{key}.json", previous.payload)
    write_json(destination, candidate.payload)
    return destination


def load_active_units(sensitive_root: Path, paths: dict[str, Path], keys) -> dict[str, UnitFile]:
    result = {}
    for key in keys:
        source = paths.get(key) or sensitive_root / "config" / "units" / f"{key}.json"
        if key not in paths and not source.exists():
            source = activate_unit_file(upgrade_source(sensitive_root, key), sensitive_root / "config", key)
        result[key] = load_unit_file(source, key)
    return result


def upgrade_source(sensitive_root: Path, key: str, legacy_root: Path | None = None) -> Path:
    """Preserve the previously active installation configuration on first upgrade."""
    if key in {"flow", "fish", "pre", "lege"}:
        return default_unit_file(key)
    legacy_root = legacy_root or Path(__file__).resolve().parents[2] / "config"
    legacy_units = legacy_root / "units.json"
    if not legacy_units.is_file():
        return default_unit_file(key)
    try:
        raw = json.loads(legacy_units.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)
        units = {unit.key: unit for unit in validate_units(raw)}
        unit = units[key]
        if len(unit.reports) != 3:
            raise UnitConfigError("Eldre statistikkoppsett må ha tre rapportroller.")
        reports = {}
        for role, marker in (("antall", "ANTALL"), ("resultater", "RESULTATER"), ("ekstraksjon", "EKSTRAKSJON")):
            matches = [report for report in unit.reports if marker in report.report_id.upper()]
            if len(matches) != 1:
                raise UnitConfigError(f"Kan ikke entydig migrere rapportrollen {role}.")
            report = matches[0]
            reports[role] = {"job_key": report.job_key, "fetch_report_id": report.fetch_report_id,
                             "report_id": report.report_id, "analysis_codes": list(report.analysis_codes or unit.analysis_codes)}
        payload = {"schema_version": 1, "key": key, "label": unit.label, "profile": unit.profile,
                   "statistics": reports, "backlog": None}
        originals = {"units.json": raw}
        if key == "hemato":
            payload["backlog"] = {}
            for section in ("report", "analyses", "columns"):
                filename = f"backlog-{section}.json"
                content = json.loads((legacy_root / filename).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)
                originals[filename] = content
                payload["backlog"][section] = content
        digest = hashlib.sha256(json.dumps(originals, sort_keys=True).encode()).hexdigest()
        root = sensitive_root / "config" / "migration" / digest
        source = root / f"{key}.json"
        write_json(source, payload)
        load_unit_file(source, key)
        for name, content in originals.items():
            write_json(root / "originals" / name, content)
        return source
    except (ValueError, KeyError, OSError) as exc:
        raise UnitConfigError(f"CONFIG_MIGRATION: Eldre oppsett kunne ikke overføres. Originalene er bevart. {exc}") from exc


def materialize_snapshot(sensitive_root: Path, definitions: dict[str, UnitFile]) -> Path:
    """Legacy pipeline inputs are pinned to the exact validated unit versions."""
    digest = hashlib.sha256("".join(f"{k}:{v.digest}" for k, v in sorted(definitions.items())).encode()).hexdigest()
    root = sensitive_root / "config" / "revisions" / digest
    write_json(root / "units.json", {"units": {key: definition.legacy_statistics() for key, definition in definitions.items()}})
    for key, definition in definitions.items():
        write_json(root / f"{key}.json", definition.payload)
        if definition.payload.get("backlog"):
            for section, content in definition.payload["backlog"].items():
                write_json(root / key / f"backlog-{section}.json", content)
    return root
