from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .archive import RawArchive
from ._backlog.export import export_backlog_history
from .backlog import BacklogProcessor
from .database import MolStatDatabase
from .lvms.report import ReportRequest
from .modules import DEFAULT_UNITS, JobKind, UnitRegistry
from .publisher import SharePointPublisher


FetchedReport = tuple[ReportRequest, Path]


@dataclass(frozen=True, slots=True)
class CapabilityRun:
    unit_key: str
    job_kind: JobKind
    summary: Mapping[str, object]
    error: BaseException | None = field(default=None, repr=False)


class MolStatSystem:
    def __init__(
        self,
        *,
        database: MolStatDatabase,
        archive: RawArchive,
        statistics_processors: Mapping[str, Any],
        backlog_processor: BacklogProcessor,
        publisher: SharePointPublisher | Mapping[str, SharePointPublisher],
        sharepoint_root: Path,
        work_root: Path,
        statistics_fetch: Callable[
            [Sequence[str] | None],
            Mapping[str, Sequence[FetchedReport]],
        ],
        backlog_fetch: Callable[[], FetchedReport],
        backlog_publisher: SharePointPublisher | None = None,
        units: UnitRegistry = DEFAULT_UNITS,
    ) -> None:
        self.database = database
        self.archive = archive
        self.statistics_processors = statistics_processors
        self.backlog_processor = backlog_processor
        self.publisher = publisher
        self.sharepoint_root = sharepoint_root
        self.work_root = work_root
        self.statistics_fetch = statistics_fetch
        self.backlog_fetch = backlog_fetch
        self.backlog_publisher = backlog_publisher
        self.units = units

    def run_statistics(self) -> dict[str, int]:
        fetched = self.statistics_fetch(None)
        total_rows = 0
        for unit_key, reports in fetched.items():
            summary = self._process_statistics(unit_key, reports)
            total_rows += int(summary["rows"])
        return {"rows": total_rows, "units": len(fetched)}

    def run_statistics_unit(self, unit_key: str) -> dict[str, int]:
        capability = self.units.require(unit_key).capability("statistics")
        del capability
        fetched = self.statistics_fetch((unit_key,))
        if tuple(fetched) != (unit_key,):
            raise RuntimeError(
                f"Statistikkhenting returnerte ikke bare {unit_key}."
            )
        return self._process_statistics(unit_key, fetched[unit_key])

    def _process_statistics(
        self,
        unit_key: str,
        reports: Sequence[FetchedReport],
    ) -> dict[str, int]:
        capability = self.units.require(unit_key).capability("statistics")
        processor = self.statistics_processors.get(unit_key)
        if processor is None:
            raise ValueError(f"Statistikkprosessor mangler for {unit_key}.")
        archived = tuple(self._archive_and_remove(item) for item in reports)
        output_dir = self.work_root / f"statistics-{unit_key}-{uuid4().hex}"
        result = processor.process(unit_key, archived, output_dir)
        active_publisher = (
            self.publisher[unit_key]
            if isinstance(self.publisher, Mapping)
            else self.publisher
        )
        active_publisher.publish(
            {
                "antall.csv": result.antall,
                "resultater.csv": result.resultater,
            },
            self.sharepoint_root / capability.sharepoint_folder,
        )
        return {
            "rows": sum(int(value) for value in result.row_counts.values()),
            "units": 1,
        }

    def run_backlog(self) -> dict[str, int]:
        return self.run_backlog_unit("hemato")

    def run_backlog_unit(self, unit_key: str) -> dict[str, int]:
        capability = self.units.require(unit_key).capability("backlog")
        if unit_key != "hemato":
            raise ValueError(f"Restansehenting er ikke konfigurert for {unit_key}.")
        request, source = self.backlog_fetch()
        if request.kind != "backlog" or request.unit != unit_key:
            raise ValueError("Restanserapporten har feil type eller enhet.")
        try:
            imported = self.backlog_processor.import_snapshot(source, self.database)
        finally:
            source.unlink(missing_ok=True)
        published_rows = 0
        if self.backlog_publisher is not None:
            filename = capability.publication_files[0][0]
            output_dir = self.work_root / f"backlog-{unit_key}-{uuid4().hex}"
            candidate = output_dir / filename
            published_rows = export_backlog_history(
                self.database,
                candidate,
                unit_key=unit_key,
            )
            self.backlog_publisher.publish(
                {filename: candidate},
                self.sharepoint_root / capability.sharepoint_folder,
            )
        with self.database._connect() as connection:
            snapshots = int(
                connection.execute(
                    """
                    SELECT COUNT(DISTINCT observed_at)
                    FROM backlog_snapshot
                    WHERE unit_key = ?
                    """,
                    (unit_key,),
                ).fetchone()[0]
            )
        return {
            "rows": imported.rows_read,
            "invalid": imported.invalid_rows,
            "excluded": imported.excluded_rows,
            "snapshots": snapshots,
            "published_rows": published_rows,
        }

    def _run_capability(
        self,
        unit_key: str,
        job_kind: JobKind,
    ) -> Mapping[str, object]:
        if job_kind == "statistics":
            return self.run_statistics_unit(unit_key)
        if job_kind == "backlog":
            return self.run_backlog_unit(unit_key)
        raise ValueError(f"Ukjent kapabilitet: {job_kind}")

    def run_unit(self, unit_key: str) -> tuple[CapabilityRun, ...]:
        unit = self.units.require(unit_key)
        if unit.status != "active":
            raise ValueError(f"Enheten {unit.display_name} kommer senere.")
        return tuple(
            self._capture_capability(unit.key, capability.job_kind)
            for capability in unit.capabilities
        )

    def run_all(
        self, enabled_units: Sequence[str]
    ) -> tuple[CapabilityRun, ...]:
        for key in enabled_units:
            self.units.require(key)
        return tuple(
            result
            for unit in self.units.active(enabled_units)
            for result in self.run_unit(unit.key)
        )

    def run_job(
        self,
        job_kind: JobKind,
        enabled_units: Sequence[str],
    ) -> tuple[CapabilityRun, ...]:
        return tuple(
            self._capture_capability(unit.key, job_kind)
            for unit in self.units.for_job(job_kind, enabled_units)
        )

    def _capture_capability(
        self,
        unit_key: str,
        job_kind: JobKind,
    ) -> CapabilityRun:
        try:
            summary = self._run_capability(unit_key, job_kind)
        except Exception as error:
            return CapabilityRun(unit_key, job_kind, {}, error=error)
        return CapabilityRun(unit_key, job_kind, summary)

    def public_snapshot(self, now: datetime) -> dict[str, object]:
        return self.backlog_processor.public_snapshot(self.database, now)

    def _archive_and_remove(self, fetched: FetchedReport) -> Path:
        request, source = fetched
        archived = self.archive.store(source, request)
        source.unlink()
        return archived.path
