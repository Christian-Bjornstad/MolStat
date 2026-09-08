"""Explicit registry for MolStat data modules.

The registry contains metadata only.  Processor implementations remain tested
Python code and cannot be loaded dynamically from user configuration.
"""

from __future__ import annotations

from collections.abc import Iterator
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


@dataclass(frozen=True, slots=True)
class DataModule:
    key: str
    display_name: str
    job_kind: JobKind
    schedule_key: str
    processor_profile: str
    sharepoint_folder: str
    publication_files: tuple[tuple[str, frozenset[str]], ...]
    status_fields: tuple[str, ...]

    @property
    def allowed_columns(self) -> Mapping[str, frozenset[str]]:
        return MappingProxyType(dict(self.publication_files))


class ModuleRegistry:
    def __init__(self, modules: tuple[DataModule, ...]) -> None:
        by_key = {module.key: module for module in modules}
        if len(by_key) != len(modules):
            raise ValueError("Modulnøkler må være unike.")
        self._modules = modules
        self._by_key = MappingProxyType(by_key)

    def __iter__(self) -> Iterator[DataModule]:
        return iter(self._modules)

    def __len__(self) -> int:
        return len(self._modules)

    def require(self, key: str) -> DataModule:
        try:
            return self._by_key[key]
        except KeyError as error:
            raise KeyError(f"Ukjent MolStat-modul: {key}") from error

    def for_job(self, job_kind: JobKind) -> tuple[DataModule, ...]:
        return tuple(
            module for module in self._modules if module.job_kind == job_kind
        )

    def single_for_job(self, job_kind: JobKind) -> DataModule:
        matches = self.for_job(job_kind)
        if len(matches) != 1:
            raise ValueError(
                f"Forventet én modul for jobbtypen {job_kind}, fant {len(matches)}."
            )
        return matches[0]


DEFAULT_MODULES = ModuleRegistry(
    (
        DataModule(
            key="hemato",
            display_name="Hemato",
            job_kind="statistics",
            schedule_key="statistics_daily",
            processor_profile="hemato",
            sharepoint_folder="hemato",
            publication_files=(
                ("antall.csv", frozenset(ANTALL_COLUMNS)),
                ("resultater.csv", frozenset(RESULTATER_COLUMNS)),
            ),
            status_fields=("rows",),
        ),
        DataModule(
            key="solide",
            display_name="Solide",
            job_kind="statistics",
            schedule_key="statistics_daily",
            processor_profile="solide",
            sharepoint_folder="solide",
            publication_files=(
                ("antall.csv", frozenset(SOLIDE_ANTALL_COLUMNS)),
                ("resultater.csv", frozenset(SOLIDE_RESULTATER_COLUMNS)),
            ),
            status_fields=("rows",),
        ),
        DataModule(
            key="proveflyt",
            display_name="Prøveflyt",
            job_kind="backlog",
            schedule_key="backlog_hourly",
            processor_profile="backlog",
            sharepoint_folder="Prøveflyt",
            publication_files=(
                ("restansehistorikk.csv", frozenset(BACKLOG_PUBLIC_COLUMNS)),
            ),
            status_fields=(
                "rows",
                "invalid",
                "excluded",
                "snapshots",
                "published_rows",
            ),
        ),
    )
)
