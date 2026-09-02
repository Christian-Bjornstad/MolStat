"""Konfigurasjon og domenemodeller for MolPat Puls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal


class ConfigError(ValueError):
    """Konfigurasjonen er ugyldig eller kan ikke lastes."""


@dataclass(frozen=True)
class UnitConfig:
    """En klinisk enhet (f.eks. hemato)."""
    key: str
    label: str


@dataclass(frozen=True)
class ThresholdsConfig:
    """Standard terskler for aldersstatus (timer)."""
    warning_hours: int = 24
    critical_hours: int = 48


@dataclass(frozen=True)
class AnalysisConfig:
    """Én analysedefinisjon fra katalogen."""
    code: str
    label: str
    group: str
    priority: Literal["critical", "standard"]
    enabled: bool = True
    # Per-analyse overstyring av globale terskler (None = bruk standard)
    warning_hours: int | None = None
    critical_hours: int | None = None
    source_codes: tuple[str, ...] = ()
    report_group: str = ""

    def effective_warning(self, defaults: ThresholdsConfig) -> int:
        return self.warning_hours if self.warning_hours is not None else defaults.warning_hours

    def effective_critical(self, defaults: ThresholdsConfig) -> int:
        return self.critical_hours if self.critical_hours is not None else defaults.critical_hours


@dataclass(frozen=True)
class AppConfig:
    """Hovedkonfigurasjon for MolPat Puls."""
    report_id: str
    unit: UnitConfig
    thresholds: ThresholdsConfig
    analyses: tuple[AnalysisConfig, ...]

    @property
    def enabled_codes(self) -> tuple[str, ...]:
        """Alle koder med enabled=True."""
        return tuple(a.code for a in self.analyses if a.enabled)

    @property
    def source_groups(self) -> dict[str, tuple[str, ...]]:
        return {
            analysis.code: analysis.source_codes
            for analysis in self.analyses
            if analysis.enabled and analysis.source_codes
        }

    def analysis_by_code(self, code: str) -> AnalysisConfig | None:
        for a in self.analyses:
            if a.code == code:
                return a
        return None

    def analyses_in_group(self, group: str) -> tuple[AnalysisConfig, ...]:
        return tuple(a for a in self.analyses if a.group == group and a.enabled)


def _validate_analysis(item: object, idx: int) -> AnalysisConfig:
    if not isinstance(item, dict):
        raise ConfigError(f"analyse[{idx}]: må være et objekt")
    code = item.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ConfigError(f"analyse[{idx}]: 'code' mangler eller er tom")
    label = item.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ConfigError(f"analyse[{idx}]: 'label' mangler eller er tom")
    group = item.get("group")
    if not isinstance(group, str) or not group.strip():
        raise ConfigError(f"analyse[{idx}]: 'group' mangler eller er tom")
    priority = item.get("priority")
    if priority not in ("critical", "standard"):
        raise ConfigError(f"analyse[{idx}]: 'priority' må være 'critical' eller 'standard'")
    enabled = item.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError(f"analyse[{idx}]: 'enabled' må være boolean")
    warning_hours = item.get("warning_hours")
    if warning_hours is not None and (not isinstance(warning_hours, int) or warning_hours < 0):
        raise ConfigError(f"analyse[{idx}]: 'warning_hours' må være positivt heltall eller null")
    critical_hours = item.get("critical_hours")
    if critical_hours is not None and (not isinstance(critical_hours, int) or critical_hours < 0):
        raise ConfigError(f"analyse[{idx}]: 'critical_hours' må være positivt heltall eller null")
    source_codes_raw = item.get("source_codes", [])
    if not isinstance(source_codes_raw, list) or any(
        not isinstance(value, str) or not value.strip()
        for value in source_codes_raw
    ):
        raise ConfigError(f"analyse[{idx}]: 'source_codes' må være en liste med koder")
    report_group = item.get("report_group", "")
    if not isinstance(report_group, str):
        raise ConfigError(f"analyse[{idx}]: 'report_group' må være tekst")
    return AnalysisConfig(
        code=code.strip(),
        label=label.strip(),
        group=group.strip(),
        priority=priority,
        enabled=enabled,
        warning_hours=warning_hours,
        critical_hours=critical_hours,
        source_codes=tuple(value.strip() for value in source_codes_raw),
        report_group=report_group.strip(),
    )


def load_app_config(path: Path) -> AppConfig:
    """Last og valider applikasjonskonfigurasjonen."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"kunne ikke lese konfigurasjon: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"ugyldig JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("rot må være et objekt")

    schema_version = raw.get("schema_version")
    if schema_version != 1:
        raise ConfigError(f"ukjent schema_version: {schema_version}")

    report_id = raw.get("report_id")
    if not isinstance(report_id, str) or not report_id.strip():
        raise ConfigError("'report_id' mangler")

    unit_raw = raw.get("unit")
    if not isinstance(unit_raw, dict):
        raise ConfigError("'unit' må være et objekt")
    unit = UnitConfig(
        key=str(unit_raw.get("key", "")).strip(),
        label=str(unit_raw.get("label", "")).strip(),
    )
    if not unit.key:
        raise ConfigError("'unit.key' mangler")
    if not unit.label:
        raise ConfigError("'unit.label' mangler")

    thresholds_raw = raw.get("thresholds", {})
    if not isinstance(thresholds_raw, dict):
        raise ConfigError("'thresholds' må være et objekt")
    thresholds = ThresholdsConfig(
        warning_hours=int(thresholds_raw.get("warning_hours", 24)),
        critical_hours=int(thresholds_raw.get("critical_hours", 48)),
    )
    if thresholds.warning_hours <= 0 or thresholds.critical_hours <= 0:
        raise ConfigError("terskler må være positive heltall")
    if thresholds.warning_hours >= thresholds.critical_hours:
        raise ConfigError("warning_hours må være mindre enn critical_hours")

    analyses_raw = raw.get("analyses")
    if not isinstance(analyses_raw, list) or not 1 <= len(analyses_raw) <= 500:
        raise ConfigError("'analyses' må være en liste med 1-500 elementer")

    analyses: list[AnalysisConfig] = []
    seen: set[str] = set()
    for idx, item in enumerate(analyses_raw):
        parsed = _validate_analysis(item, idx)
        # Materialiser globale standardverdier i hver analyse. Dermed er
        # analysedefinisjonen selvstendig når den sendes videre til tavla.
        analysis = AnalysisConfig(
            code=parsed.code,
            label=parsed.label,
            group=parsed.group,
            priority=parsed.priority,
            enabled=parsed.enabled,
            warning_hours=(
                parsed.warning_hours
                if parsed.warning_hours is not None
                else thresholds.warning_hours
            ),
            critical_hours=(
                parsed.critical_hours
                if parsed.critical_hours is not None
                else thresholds.critical_hours
            ),
            source_codes=parsed.source_codes,
            report_group=parsed.report_group,
        )
        if analysis.warning_hours >= analysis.critical_hours:
            raise ConfigError(
                f"analyse[{idx}]: warning_hours må være mindre enn critical_hours"
            )
        if analysis.code in seen:
            raise ConfigError(f"duplikat analysekode: {analysis.code}")
        seen.add(analysis.code)
        analyses.append(analysis)

    return AppConfig(
        report_id=report_id.strip(),
        unit=unit,
        thresholds=thresholds,
        analyses=tuple(analyses),
    )


def load_restanse_columns(path: Path) -> dict:
    """Last kolonnekartlegging for RESTANSE-CSV (valgfri overstyring)."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"kunne ikke lese kolonnekonfig: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"ugyldig JSON i kolonnekonfig: {exc}") from exc

    defaults = {
        "classifier_version": 2,
        "delimiter": ";",
        "encoding": "windows-1252",
        "columns": {
            "sample_id": "Sample ID",
            "analysis_code": "Analyse",
            "created_at": "Tidspunkt",
            "status": "Status",
        },
        "completed_values": ["completed", "ferdig", "besvart"],
    }

    if not isinstance(raw, dict):
        return defaults

    # Shallow merge for each section
    classifier_version = raw.get("classifier_version")
    if isinstance(classifier_version, int) and classifier_version > 0:
        defaults["classifier_version"] = classifier_version

    delimiter = raw.get("delimiter")
    if isinstance(delimiter, str) and len(delimiter) == 1:
        defaults["delimiter"] = delimiter

    encoding = raw.get("encoding")
    if isinstance(encoding, str) and encoding.strip():
        defaults["encoding"] = encoding.strip()

    columns = raw.get("columns")
    if isinstance(columns, dict):
        for k, v in columns.items():
            if isinstance(v, str) and v.strip():
                defaults["columns"][k] = v.strip()

    completed = raw.get("completed_values")
    if isinstance(completed, list) and completed:
        defaults["completed_values"] = [str(v).strip() for v in completed if isinstance(v, str)]

    return defaults