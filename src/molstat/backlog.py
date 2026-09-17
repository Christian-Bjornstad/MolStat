from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
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
from ._backlog.history import (
    build_detail_history_rows,
    build_history_rows,
    hour_slot,
)
from .database import MolStatDatabase
from .registry import OccurrenceInput, SampleRegistry

ImportResult = CsvImportResult


class BacklogProcessor:
    def __init__(
        self,
        config: AppConfig,
        contract: CsvContract,
        *,
        now: Callable[[], datetime] = datetime.now,
        stale_after: timedelta = timedelta(hours=2),
        analysis_lookup: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        self.config = config
        self.contract = contract
        self._now = now
        self.stale_after = stale_after
        self.analysis_lookup = analysis_lookup or {}

    def import_snapshot(
        self,
        csv_path: Path,
        database: MolStatDatabase,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> ImportResult:
        imported = read_restanse_csv(
            csv_path,
            self.contract,
            analysis_groups=self.config.source_groups,
        )
        if imported.rows_read == 0:
            raise CsvImportError("RESTANSE-filen inneholder ingen datarader.")
        observed_at = self._now()
        history_rows = build_history_rows(
            self.config,
            imported.samples,
            observed_at,
            invalid_rows=imported.invalid_rows,
            excluded_rows=imported.excluded_rows,
            classifier_version=self.contract.classifier_version,
        )
        detail_rows = build_detail_history_rows(
            self.config,
            imported.details,
            observed_at,
            analysis_lookup=self.analysis_lookup,
            classifier_version=self.contract.classifier_version,
        )
        observed_at_text = observed_at.isoformat()
        with database._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                interval_from = date_from or observed_at.date()
                interval_to = date_to or observed_at.date()
                run_cursor = connection.execute(
                    """
                    INSERT INTO import_run(
                        kind, unit_key, date_from, date_to, started_at,
                        finished_at, status, source_fingerprint, row_count,
                        invalid_rows, excluded_rows
                    ) VALUES ('backlog', ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?)
                    """,
                    (
                        self.config.unit.key,
                        interval_from.isoformat(),
                        interval_to.isoformat(),
                        observed_at_text,
                        observed_at_text,
                        imported.fingerprint,
                        imported.rows_read,
                        imported.invalid_rows,
                        imported.excluded_rows,
                    ),
                )
                import_run_id = int(run_cursor.lastrowid)
                registry = SampleRegistry(database)
                registered_details = [
                    (
                        detail,
                        registry.register_occurrence_in_transaction(
                            connection,
                            OccurrenceInput(
                                source_system="LVMS",
                                sample_number=detail.sample_id,
                                analysis_code=detail.analysis_code,
                                ordered_at=detail.ordered_at,
                                source_occurrence_id=(
                                    detail.source_occurrence_id or None
                                ),
                                source_kind="backlog",
                            ),
                            observed_at=observed_at,
                            import_run_id=import_run_id,
                        ),
                    )
                    for detail in imported.details
                ]
                detail_slot_exists = connection.execute(
                    """
                    SELECT 1
                    FROM backlog_snapshot
                    WHERE observed_at = ? AND unit_key = ?
                      AND classifier_version = ?
                    LIMIT 1
                    """,
                    (
                        detail_rows[0].observed_at.isoformat()
                        if detail_rows
                        else hour_slot(observed_at).isoformat(),
                        self.config.unit.key,
                        self.contract.classifier_version,
                    ),
                ).fetchone() is not None
                connection.execute(
                    "DELETE FROM backlog_current WHERE unit_key = ?",
                    (self.config.unit.key,),
                )
                connection.executemany(
                    """
                    INSERT INTO backlog_current(
                        occurrence_id, import_run_id, unit_key, analysis_group,
                        workflow_stage, collected_at, arrived_at,
                        analysis_status, preliminary_status, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            registered.occurrence_id,
                            import_run_id,
                            self.config.unit.key,
                            detail.analysis_group,
                            detail.stage.value,
                            (
                                detail.collected_at.isoformat()
                                if detail.collected_at is not None
                                else None
                            ),
                            (
                                detail.arrived_at.isoformat()
                                if detail.arrived_at is not None
                                else None
                            ),
                            detail.analysis_status,
                            detail.preliminary_status,
                            observed_at_text,
                        )
                        for detail, registered in registered_details
                    ),
                )
                connection.execute("DELETE FROM backlog_sample WHERE unit_key = ?", (self.config.unit.key,))
                connection.executemany(
                    """
                    INSERT INTO backlog_sample(
                        unit_key,
                        sample_key,
                        analysis_group,
                        ordered_at,
                        arrived_at,
                        workflow_stage,
                        observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            self.config.unit.key,
                            sample.sample_id,
                            sample.analysis_code,
                            sample.ordered_at.isoformat(),
                            (
                                sample.arrived_at.isoformat()
                                if sample.arrived_at is not None
                                else None
                            ),
                            sample.stage.value,
                            observed_at_text,
                        )
                        for sample in imported.samples
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO backlog_snapshot(
                        observed_at,
                        unit_key,
                        analysis_code,
                        analysis_label,
                        ready_count,
                        awaiting_approval_count,
                        in_transit_count,
                        overdue_count,
                        median_ready_hours,
                        oldest_ready_hours,
                        severity,
                        invalid_rows,
                        excluded_rows,
                        source_is_fresh,
                        classifier_version,
                        source_fingerprint
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        (
                            row.observed_at.isoformat(),
                            row.unit_key,
                            row.analysis_code,
                            row.analysis_label,
                            row.ready_count,
                            row.awaiting_approval_count,
                            row.in_transit_count,
                            row.overdue_count,
                            row.median_ready_hours,
                            row.oldest_ready_hours,
                            row.severity.value,
                            row.invalid_rows,
                            row.excluded_rows,
                            int(row.source_is_fresh),
                            row.classifier_version,
                            imported.fingerprint,
                        )
                        for row in history_rows
                    ),
                )
                if not detail_slot_exists:
                    connection.executemany(
                        """
                        INSERT INTO backlog_detail_snapshot(
                            observed_at, unit_key, row_number, material,
                            analysis_code, nucleic_acid, report_group,
                            analysis_group_code, analysis_group_label,
                            collected_at, arrived_at, ordered_at,
                            analysis_priority, request_priority, analysis_status,
                            preliminary_status, workflow_stage, response_deadline,
                            analysis_result, external_analysis_comment,
                            classifier_version, source_fingerprint, molstat_key
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            (
                                row.observed_at.isoformat(),
                                row.unit_key,
                                row_number,
                                row.material,
                                row.analysis_code,
                                row.nucleic_acid,
                                "",
                                row.analysis_group_code,
                                row.analysis_group_label,
                                row.collected_at.isoformat() if row.collected_at else None,
                                row.arrived_at.isoformat() if row.arrived_at else None,
                                row.ordered_at.isoformat(),
                                row.analysis_priority,
                                row.request_priority,
                                row.analysis_status,
                                row.preliminary_status,
                                row.workflow_stage,
                                row.response_deadline,
                                row.analysis_result,
                                row.external_analysis_comment,
                                row.classifier_version,
                                imported.fingerprint,
                                registered.molstat_key,
                            )
                            for row_number, (
                                row,
                                (_detail, registered),
                            ) in enumerate(
                                zip(detail_rows, registered_details, strict=True),
                                start=1,
                            )
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
                WHERE unit_key = ?
                """, (self.config.unit.key,)
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
