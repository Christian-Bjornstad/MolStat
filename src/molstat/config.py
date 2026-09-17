from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any


SETTINGS_SCHEMA_VERSION = 2
ACTIVE_UNIT_KEYS = ("hemato", "solide")


@dataclass(frozen=True, slots=True)
class MolStatSettings:
    sensitive_root: Path
    sharepoint_root: Path | None = None
    statistics_hour: int = 5
    backlog_first_hour: int = 6
    backlog_last_hour: int = 18
    statistics_lookup_paths: dict[str, Path] = field(default_factory=dict)
    lvms_config_path: Path | None = None
    lvms_url: str = ""
    enabled_units: tuple[str, ...] = ACTIVE_UNIT_KEYS
    unit_config_paths: dict[str, Path] = field(default_factory=dict)

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if self.sharepoint_root is not None and _same_path(
            self.sensitive_root, self.sharepoint_root
        ):
            errors.append("K-sensitiv og SharePoint må være ulike mapper.")
        elif self.sharepoint_root is not None:
            sensitive, public = self.sensitive_root.resolve(), self.sharepoint_root.resolve()
            if sensitive.is_relative_to(public) or public.is_relative_to(sensitive):
                errors.append("K-sensitiv og SharePoint kan ikke ligge inni hverandre.")
        if not 0 <= self.statistics_hour <= 23:
            errors.append("Klokkeslett for statistikk må være mellom 0 og 23.")
        if not 0 <= self.backlog_first_hour <= 23:
            errors.append("Første restansetime må være mellom 0 og 23.")
        if not 0 <= self.backlog_last_hour <= 23:
            errors.append("Siste restansetime må være mellom 0 og 23.")
        if self.backlog_first_hour > self.backlog_last_hour:
            errors.append("Første restansetime kan ikke være etter siste time.")
        unknown = set(self.enabled_units) - set(ACTIVE_UNIT_KEYS)
        if unknown:
            errors.append("Ukjent aktiv enhet: " + ", ".join(sorted(unknown)))
        return tuple(errors)

    def to_transfer_payload(self) -> dict[str, object]:
        return {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "sensitive_root": str(self.sensitive_root),
            "sharepoint_root": (
                str(self.sharepoint_root)
                if self.sharepoint_root is not None
                else None
            ),
            "lvms_url": self.lvms_url,
            "schedules": {
                "statistics_hour": self.statistics_hour,
                "backlog_first_hour": self.backlog_first_hour,
                "backlog_last_hour": self.backlog_last_hour,
            },
            "units": {
                key: {
                    "enabled": key in self.enabled_units,
                    "statistics_lookup_path": str(
                        self.statistics_lookup_paths.get(key, "")
                    ),
                    "config_path": str(self.unit_config_paths.get(key, "")),
                }
                for key in ACTIVE_UNIT_KEYS
            },
        }

    @classmethod
    def from_transfer_payload(
        cls, payload: Mapping[str, object]
    ) -> MolStatSettings:
        settings = cls._from_versioned_payload(
            payload, allow_local_runtime=False
        )
        _raise_validation_error(settings)
        return settings

    def save(self, path: Path) -> None:
        payload = self.to_transfer_payload()
        payload["lvms_config_path"] = (
            str(self.lvms_config_path)
            if self.lvms_config_path is not None
            else None
        )
        _write_json_atomic(path, payload)

    def export_to(self, path: Path) -> None:
        _write_json_atomic(path, self.to_transfer_payload())

    @classmethod
    def load(cls, path: Path) -> MolStatSettings:
        payload = _read_json_object(path)
        payload.pop("power_bi_report_url", None)
        if "schema_version" not in payload:
            return cls._from_legacy_payload(payload)
        return cls._from_versioned_payload(payload, allow_local_runtime=True)

    @classmethod
    def import_from(cls, path: Path) -> MolStatSettings:
        payload = _read_json_object(path)
        return cls.from_transfer_payload(payload)

    @classmethod
    def _from_legacy_payload(
        cls, payload: Mapping[str, object]
    ) -> MolStatSettings:
        sensitive_root = _required_string(payload, "sensitive_root")
        sharepoint_root = _optional_string(payload, "sharepoint_root")
        lookup_raw = payload.get("statistics_lookup_paths", {})
        if not isinstance(lookup_raw, Mapping):
            raise ValueError("Lookup-stier må være et objekt.")
        lookups = {
            str(unit): Path(value)
            for unit, value in lookup_raw.items()
            if isinstance(value, str) and value
        }
        lvms_config = _optional_string(payload, "lvms_config_path")
        settings = cls(
            sensitive_root=Path(sensitive_root),
            sharepoint_root=Path(sharepoint_root) if sharepoint_root else None,
            statistics_hour=_legacy_hour(payload, "statistics_hour", 5),
            backlog_first_hour=_legacy_hour(payload, "backlog_first_hour", 6),
            backlog_last_hour=_legacy_hour(payload, "backlog_last_hour", 18),
            statistics_lookup_paths=lookups,
            lvms_config_path=Path(lvms_config) if lvms_config else None,
            lvms_url=str(payload.get("lvms_url", "")),
            enabled_units=ACTIVE_UNIT_KEYS,
        )
        return settings

    @classmethod
    def _from_versioned_payload(
        cls,
        payload: Mapping[str, object],
        *,
        allow_local_runtime: bool,
    ) -> MolStatSettings:
        version = payload.get("schema_version")
        if type(version) is not int or version != SETTINGS_SCHEMA_VERSION:
            raise ValueError("Ukjent skjemaversjon for MolStat-innstillinger.")

        schedules = payload.get("schedules")
        if not isinstance(schedules, Mapping):
            raise ValueError("Innstillingsfilen mangler gyldige klokkeslett.")
        units = payload.get("units")
        if not isinstance(units, Mapping):
            raise ValueError("Innstillingsfilen mangler gyldige enheter.")
        unknown_units = set(map(str, units)) - set(ACTIVE_UNIT_KEYS)
        if unknown_units:
            raise ValueError(
                "Ukjent enhetsnøkkel: " + ", ".join(sorted(unknown_units))
            )

        enabled: list[str] = []
        lookups: dict[str, Path] = {}
        configs: dict[str, Path] = {}
        for key in ACTIVE_UNIT_KEYS:
            raw_unit = units.get(key, {"enabled": False})
            if not isinstance(raw_unit, Mapping):
                raise ValueError(f"Innstillingene for {key} må være et objekt.")
            is_enabled = raw_unit.get("enabled", False)
            if type(is_enabled) is not bool:
                raise ValueError(f"Aktivering for {key} må være sann eller usann.")
            if is_enabled:
                enabled.append(key)
            lookup = raw_unit.get("statistics_lookup_path", "")
            if not isinstance(lookup, str):
                raise ValueError(f"Lookup-sti for {key} må være tekst.")
            if lookup:
                lookups[key] = Path(lookup)
            config = raw_unit.get("config_path", "")
            if not isinstance(config, str):
                raise ValueError(f"Enhetsfil for {key} må være tekst.")
            if config:
                configs[key] = Path(config)

        lvms_config: str | None = None
        if allow_local_runtime:
            lvms_config = _optional_string(payload, "lvms_config_path")
        elif "lvms_config_path" in payload:
            raise ValueError("Overføringsfilen inneholder lokale runtime-data.")

        settings = cls(
            sensitive_root=Path(_required_string(payload, "sensitive_root")),
            sharepoint_root=(
                Path(value)
                if (value := _optional_string(payload, "sharepoint_root"))
                else None
            ),
            statistics_hour=_required_hour(schedules, "statistics_hour"),
            backlog_first_hour=_required_hour(schedules, "backlog_first_hour"),
            backlog_last_hour=_required_hour(schedules, "backlog_last_hour"),
            statistics_lookup_paths=lookups,
            lvms_config_path=Path(lvms_config) if lvms_config else None,
            lvms_url=_required_string(payload, "lvms_url"),
            enabled_units=tuple(enabled),
            unit_config_paths=configs,
        )
        return settings


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Kunne ikke lese MolStat-innstillingene.") from error
    if not isinstance(payload, dict):
        raise ValueError("MolStat-innstillingene må være et JSON-objekt.")
    return payload


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Feltet {key} må være tekst.")
    return value


def _optional_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Feltet {key} må være tekst eller tomt.")
    return value


def _required_hour(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise ValueError(f"Feltet {key} må være et heltall.")
    return value


def _legacy_hour(payload: Mapping[str, object], key: str, default: int) -> int:
    value = payload.get(key, default)
    if type(value) is not int:
        raise ValueError(f"Feltet {key} må være et heltall.")
    return value


def _raise_validation_error(settings: MolStatSettings) -> None:
    errors = settings.validate()
    if errors:
        raise ValueError(errors[0])


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(str(first.resolve())) == os.path.normcase(
        str(second.resolve())
    )
