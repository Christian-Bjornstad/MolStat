from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import os
import shutil
from typing import Any
from uuid import uuid4

from .archive import RawArchive
from ._backlog.export import export_backlog_history
from .backlog import BacklogProcessor
from .database import MolStatDatabase
from .excel_search import publish_search_workbook, read_excel_snapshot
from .lvms.report import ReportRequest
from .modules import DEFAULT_UNITS, JobKind, UnitRegistry
from .publisher import SharePointPublisher
from .delivery import deliver


FetchedReport = tuple[ReportRequest, Path]


@dataclass(frozen=True, slots=True)
class CapabilityRun:
    unit_key: str
    job_kind: JobKind
    summary: Mapping[str, object]
    error: BaseException | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ExcelRefreshStatus:
    status: str
    generated_at: datetime
    error_type: str | None = None


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
        excel_search_path: Path | None = None,
        excel_now: Callable[[], datetime] = datetime.now,
        excel_failure_reporter: Callable[[str, BaseException], None] | None = None,
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
        self.excel_search_path = excel_search_path
        self._excel_now = excel_now
        self._excel_failure_reporter = excel_failure_reporter
        self.excel_status: ExcelRefreshStatus | None = None
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
        output_dir = self.work_root / unit_key / "statistics" / uuid4().hex
        result = processor.process(unit_key, archived, output_dir)
        if result.private_files:
            private_root = self.work_root / unit_key / "powerbi"
            private_root.mkdir(parents=True, exist_ok=True)
            for name, source in result.private_files.items():
                destination = private_root / name
                temporary = private_root / f".{name}.{uuid4().hex}.tmp"
                try:
                    shutil.copyfile(source, temporary)
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
        active_publisher = (
            self.publisher[unit_key]
            if isinstance(self.publisher, Mapping)
            else self.publisher
        )
        deliver(active_publisher,
            result.publication_files or {
                "antall.csv": result.antall,
                "resultater.csv": result.resultater,
            },
            self.sharepoint_root / capability.sharepoint_folder,
            output_dir,
        )
        excel_published = self._refresh_excel_search()
        return {
            "rows": sum(int(value) for value in result.row_counts.values()),
            "units": 1,
            "excel_published": excel_published,
        }

    def run_backlog(self) -> dict[str, int]:
        return self.run_backlog_unit("hemato")

    def run_backlog_unit(self, unit_key: str) -> dict[str, int]:
        capability = self.units.require(unit_key).capability("backlog")
        fetch = getattr(self, "backlog_fetchers", {}).get(unit_key, self.backlog_fetch)
        processor = getattr(self, "backlog_processors", {}).get(unit_key, self.backlog_processor)
        publisher = getattr(self, "backlog_publishers", {}).get(unit_key, self.backlog_publisher)
        request, source = fetch()
        if request.kind != "backlog" or request.unit != unit_key:
            raise ValueError("Restanserapporten har feil type eller enhet.")
        try:
            imported = processor.import_snapshot(
                source,
                self.database,
                date_from=request.date_from,
                date_to=request.date_to,
            )
        finally:
            source.unlink(missing_ok=True)
        published_rows = 0
        if publisher is not None:
            filename = capability.publication_files[0][0]
            output_dir = self.work_root / unit_key / "backlog" / uuid4().hex
            candidate = output_dir / filename
            published_rows = export_backlog_history(
                self.database,
                candidate,
                unit_key=unit_key,
            )
            deliver(publisher,
                {filename: candidate},
                self.sharepoint_root / capability.sharepoint_folder,
                output_dir,
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
        excel_published = self._refresh_excel_search()
        return {
            "rows": imported.rows_read,
            "invalid": imported.invalid_rows,
            "excluded": imported.excluded_rows,
            "snapshots": snapshots,
            "published_rows": published_rows,
            "excel_published": excel_published,
        }

    def _refresh_excel_search(self) -> bool:
        if self.excel_search_path is None:
            return False
        generated_at = self._excel_now()
        try:
            snapshot = read_excel_snapshot(
                self.database,
                generated_at=generated_at,
            )
            result = publish_search_workbook(snapshot, self.excel_search_path)
        except Exception as exc:
            self.excel_status = ExcelRefreshStatus(
                "failed",
                generated_at,
                type(exc).__name__,
            )
            if self._excel_failure_reporter is not None:
                try:
                    self._excel_failure_reporter("excel_search_refresh_failed", exc)
                except Exception:
                    pass
            return False
        self.excel_status = ExcelRefreshStatus(result.status, generated_at)
        return result.status == "published"

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
