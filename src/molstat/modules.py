"""Explicit registries for MolStat units and their runnable capabilities.

The registries contain metadata only. Processor implementations remain tested
Python code and cannot be loaded dynamically from user configuration.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

from ._backlog.export import BACKLOG_PUBLIC_COLUMNS
from .statistics import (
    ANTALL_COLUMNS,
    RESULTATER_COLUMNS,
    SOLIDE_ANTALL_COLUMNS,
    SOLIDE_RESULTATER_COLUMNS,
)


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
        UnitDefinition("lege", "Lege", "coming", ()),
        UnitDefinition("flow", "Flow", "coming", ()),
        UnitDefinition("pre", "Pre", "coming", ()),
        UnitDefinition("hist", "Hist", "coming", ()),
    )
)
