from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .archive import RawArchive
from ._backlog.export import export_backlog_history
from .backlog import BacklogProcessor
from .database import MolStatDatabase
from .lvms.report import ReportRequest
from .modules import DEFAULT_MODULES, ModuleRegistry
from .publisher import SharePointPublisher


FetchedReport = tuple[ReportRequest, Path]


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
        statistics_fetch: Callable[[], Mapping[str, Sequence[FetchedReport]]],
        backlog_fetch: Callable[[], FetchedReport],
        backlog_publisher: SharePointPublisher | None = None,
        modules: ModuleRegistry = DEFAULT_MODULES,
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
        self.modules = modules

    def run_statistics(self) -> dict[str, int]:
        fetched = self.statistics_fetch()
        total_rows = 0
        for unit, reports in fetched.items():
            module = self.modules.require(unit)
            if module.job_kind != "statistics":
                raise ValueError(f"Modulen {unit} er ikke en statistikkmodul.")
            processor = self.statistics_processors.get(unit)
            if processor is None:
                raise ValueError(f"Statistikkprosessor mangler for {unit}.")
            archived = tuple(self._archive_and_remove(item) for item in reports)
            output_dir = self.work_root / f"statistics-{unit}-{uuid4().hex}"
            result = processor.process(unit, archived, output_dir)
            active_publisher = (
                self.publisher[unit]
                if isinstance(self.publisher, Mapping)
                else self.publisher
            )
            active_publisher.publish(
                {
                    "antall.csv": result.antall,
                    "resultater.csv": result.resultater,
                },
                self.sharepoint_root / module.sharepoint_folder,
            )
            total_rows += sum(int(value) for value in result.row_counts.values())
        return {"rows": total_rows, "units": len(fetched)}

    def run_backlog(self) -> dict[str, int]:
        report = self.backlog_fetch()
        archived = self._archive_and_remove(report)
        imported = self.backlog_processor.import_snapshot(archived, self.database)
        published_rows = 0
        if self.backlog_publisher is not None:
            module = self.modules.single_for_job("backlog")
            output_dir = self.work_root / f"backlog-{uuid4().hex}"
            candidate = output_dir / "restansehistorikk.csv"
            published_rows = export_backlog_history(self.database, candidate)
            self.backlog_publisher.publish(
                {"restansehistorikk.csv": candidate},
                self.sharepoint_root / module.sharepoint_folder,
            )
        with self.database._connect() as connection:
            snapshots = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT observed_at) FROM backlog_snapshot"
                ).fetchone()[0]
            )
        return {
            "rows": imported.rows_read,
            "invalid": imported.invalid_rows,
            "excluded": imported.excluded_rows,
            "snapshots": snapshots,
            "published_rows": published_rows,
        }

    def public_snapshot(self, now: datetime) -> dict[str, object]:
        return self.backlog_processor.public_snapshot(self.database, now)

    def _archive_and_remove(self, fetched: FetchedReport) -> Path:
        request, source = fetched
        archived = self.archive.store(source, request)
        source.unlink()
        return archived.path
