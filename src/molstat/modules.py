"""Explicit registries for MolStat units and their runnable capabilities.

The registries contain metadata only. Processor implementations remain tested
Python code and cannot be loaded dynamically from user configuration.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Literal, Mapping

from ._backlog.export import BACKLOG_PUBLIC_COLUMNS
from .statistics import (
    ANTALL_COLUMNS,
    RESULTATER_COLUMNS,
    SOLIDE_ANTALL_COLUMNS,
    SOLIDE_RESULTATER_COLUMNS,
)
from ._statistics import flow_reports, fish_reports, pre_reports, patolog_process


JobKind = Literal["statistics", "backlog"]
UnitStatus = Literal["active", "coming"]


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    job_kind: JobKind
    schedule_key: str
    processor_profile: str
    sharepoint_folder: str
    publication_files: tuple[tuple[str, frozenset[str]], ...]
    status_fields: tuple[str, ...]

    @property
    def allowed_columns(self) -> Mapping[str, frozenset[str]]:
        return MappingProxyType(dict(self.publication_files))


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    key: str
    display_name: str
    status: UnitStatus
    capabilities: tuple[CapabilityDefinition, ...]

    def capability(self, job_kind: JobKind) -> CapabilityDefinition:
        matches = tuple(
            capability
            for capability in self.capabilities
            if capability.job_kind == job_kind
        )
        if len(matches) != 1:
            raise KeyError(
                f"Enheten {self.key} har ikke kapabiliteten {job_kind}."
            )
        return matches[0]


class UnitRegistry:
    def __init__(self, units: tuple[UnitDefinition, ...]) -> None:
        by_key = {unit.key: unit for unit in units}
        if len(by_key) != len(units):
            raise ValueError("Enhetsnøkler må være unike.")
        self._units = units
        self._by_key = MappingProxyType(by_key)

    def __iter__(self) -> Iterator[UnitDefinition]:
        return iter(self._units)

    def __len__(self) -> int:
        return len(self._units)

    def require(self, key: str) -> UnitDefinition:
        try:
            return self._by_key[key]
        except KeyError as error:
            raise KeyError(f"Ukjent MolStat-enhet: {key}") from error

    def active(
        self, enabled_keys: Sequence[str] | None = None
    ) -> tuple[UnitDefinition, ...]:
        enabled = set(enabled_keys) if enabled_keys is not None else None
        return tuple(
            unit
            for unit in self._units
            if unit.status == "active"
            and (enabled is None or unit.key in enabled)
        )

    def for_job(
        self,
        job_kind: JobKind,
        enabled_keys: Sequence[str] | None = None,
    ) -> tuple[UnitDefinition, ...]:
        return tuple(
            unit
            for unit in self.active(enabled_keys)
            if any(
                capability.job_kind == job_kind
                for capability in unit.capabilities
            )
        )


_HEMATO_STATISTICS = CapabilityDefinition(
    job_kind="statistics",
    schedule_key="statistics_daily",
    processor_profile="hemato",
    sharepoint_folder="hemato",
    publication_files=(
        ("antall.csv", frozenset(ANTALL_COLUMNS)),
        ("resultater.csv", frozenset(RESULTATER_COLUMNS)),
    ),
    status_fields=("rows",),
)

_SOLIDE_STATISTICS = CapabilityDefinition(
    job_kind="statistics",
    schedule_key="statistics_daily",
    processor_profile="solide",
    sharepoint_folder="solide",
    publication_files=(
        ("antall.csv", frozenset(SOLIDE_ANTALL_COLUMNS)),
        ("resultater.csv", frozenset(SOLIDE_RESULTATER_COLUMNS)),
    ),
    status_fields=("rows",),
)

_FLOW_STATISTICS = CapabilityDefinition(
    job_kind="statistics", schedule_key="statistics_daily",
    processor_profile="flow", sharepoint_folder="flow",
    publication_files=(("antall.csv", frozenset(flow_reports.ANTALL_FIELDS)),
                       ("resultater.csv", frozenset(flow_reports.RESULTATER_FIELDS))),
    status_fields=("rows",),
)

_FISH_STATISTICS = CapabilityDefinition(
    job_kind="statistics", schedule_key="statistics_daily",
    processor_profile="fish", sharepoint_folder="fish",
    publication_files=(("antall.csv", frozenset(fish_reports.ANTALL_FIELDS)),
                       ("resultater.csv", frozenset(fish_reports.RESULT_FIELDS))),
    status_fields=("rows",),
)

_PRE_STATISTICS = CapabilityDefinition(
    job_kind="statistics", schedule_key="statistics_daily",
    processor_profile="pre", sharepoint_folder="pre",
    publication_files=(("antall.csv", frozenset(pre_reports.ANTALL_FIELDS)),
                       ("resultater.csv", frozenset(pre_reports.RESULT_FIELDS))),
    status_fields=("rows",),
)

_LEGE_STATISTICS = CapabilityDefinition(
    job_kind="statistics", schedule_key="statistics_daily",
    processor_profile="lege", sharepoint_folder="lege",
    publication_files=(("prosess.csv", frozenset(patolog_process.FIELDS)),),
    status_fields=("rows",),
)

_STATISTICS_PROFILES = {
    "hemato": _HEMATO_STATISTICS,
    "solide": _SOLIDE_STATISTICS,
    "flow": _FLOW_STATISTICS,
    "fish": _FISH_STATISTICS,
    "pre": _PRE_STATISTICS,
    "lege": _LEGE_STATISTICS,
}

_HEMATO_BACKLOG = CapabilityDefinition(
    job_kind="backlog",
    schedule_key="backlog_hourly",
    processor_profile="backlog",
    sharepoint_folder="Prøveflyt",
    publication_files=(
        ("restansehistorikk_hemato.csv", frozenset(BACKLOG_PUBLIC_COLUMNS)),
    ),
    status_fields=(
        "rows",
        "invalid",
        "excluded",
        "snapshots",
        "published_rows",
    ),
)


def configured_registry(definitions) -> UnitRegistry:
    units = []
    for key, definition in definitions.items():
        statistics = _STATISTICS_PROFILES[definition.unit.profile]
        capabilities = [replace(statistics, sharepoint_folder=key)]
        if definition.payload.get("backlog") is not None:
            capabilities.append(replace(_HEMATO_BACKLOG, publication_files=((f"restansehistorikk_{key}.csv", frozenset(BACKLOG_PUBLIC_COLUMNS)),)))
        units.append(UnitDefinition(key, definition.unit.label, "active", tuple(capabilities)))
    return UnitRegistry(tuple(units))

DEFAULT_UNITS = UnitRegistry(
    (
        UnitDefinition(
            key="hemato",
            display_name="Hemato",
            status="active",
            capabilities=(_HEMATO_STATISTICS, _HEMATO_BACKLOG),
        ),
        UnitDefinition(
            key="solide",
            display_name="Solide",
            status="active",
            capabilities=(_SOLIDE_STATISTICS,),
        ),
        UnitDefinition("lege", "Patologer", "active", (_LEGE_STATISTICS,)),
        UnitDefinition("flow", "Flow", "active", (_FLOW_STATISTICS,)),
        UnitDefinition("fish", "FISH", "active", (_FISH_STATISTICS,)),
        UnitDefinition("pre", "Pre", "active", (_PRE_STATISTICS,)),
        UnitDefinition("hist", "Hist", "coming", ()),
    )
)
