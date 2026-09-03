from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from ._backlog.config import (
    AnalysisConfig,
    AppConfig,
    ConfigError,
    ThresholdsConfig,
    UnitConfig,
    load_app_config,
    load_restanse_columns,
)
from ._backlog.dashboard import (
    AnalysisDashboard,
    DashboardSnapshot,
    Severity,
    build_dashboard_snapshot,
)
from ._backlog.domain import Sample, WorkflowStage, parse_lvms_datetime
from ._backlog.ingestion import (
    CsvContract,
    CsvImportError,
    CsvImportResult,
    classify_workflow,
    file_fingerprint,
    read_restanse_csv,
)
from .database import MolStatDatabase

ImportResult = CsvImportResult


class BacklogProcessor:
    def __init__(
        self,
        config: AppConfig,
        contract: CsvContract,
        *,
        now: Callable[[], datetime] = datetime.now,
        stale_after: timedelta = timedelta(hours=2),
    ) -> None:
        self.config = config
        self.contract = contract
        self._now = now
        self.stale_after = stale_after

    def import_snapshot(
        self,
        csv_path: Path,
        database: MolStatDatabase,
    ) -> ImportResult:
        imported = read_restanse_csv(
            csv_path,
            self.contract,
            analysis_groups=self.config.source_groups,
        )
        observed_at = self._now().isoformat()
        with database._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("DELETE FROM backlog_sample")
                connection.executemany(
                    """
                    INSERT INTO backlog_sample(
                        sample_key,
                        analysis_group,
                        ordered_at,
                        arrived_at,
                        workflow_stage,
                        observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            sample.sample_id,
                            sample.analysis_code,
                            sample.ordered_at.isoformat(),
                            (
                                sample.arrived_at.isoformat()
                                if sample.arrived_at is not None
                                else None
                            ),
                            sample.stage.value,
                            observed_at,
                        )
                        for sample in imported.samples
                    ),
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return imported

    def public_snapshot(
        self,
        database: MolStatDatabase,
        now: datetime,
    ) -> dict[str, object]:
        with database._connect() as connection:
            rows = connection.execute(
                """
                SELECT sample_key, analysis_group, ordered_at, arrived_at,
                       workflow_stage, observed_at
                FROM backlog_sample
                """
            ).fetchall()
        samples = tuple(
            Sample(
                sample_id=str(row[0]),
                analysis_code=str(row[1]),
                ordered_at=datetime.fromisoformat(row[2]),
                arrived_at=(
                    datetime.fromisoformat(row[3]) if row[3] is not None else None
                ),
                stage=WorkflowStage(row[4]),
            )
            for row in rows
        )
        source_updated_at = (
            max(datetime.fromisoformat(row[5]) for row in rows) if rows else None
        )
        return build_dashboard_snapshot(
            self.config,
            samples,
            now,
            self.stale_after,
            source_updated_at=source_updated_at,
        ).to_public_dict()
