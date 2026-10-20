from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import re
import time
from uuid import uuid4

from .storage_layout import StorageLayout
from .archive import RawArchive, remove_archived_download
from .lvms.batch_runner import run_report_batch
from .lvms.report import ReportRequest
from .lvms.report_job import ReportInterval, ReportJob, batch_filename
from .statistics import Unit, load_units
from .failures import RunFailure
from ._writer_lease import checkpoint_writer_lease


_WINDOW = re.compile(
    r"__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})(?:__r\d+)?\.csv$"
)
BACKLOG_FROM = date(2024, 1, 1)


@dataclass(frozen=True, slots=True)
class ReportDefinition:
    report_type: str
    category: str
    report_id: str
    report_groups: tuple[str, ...]
    analysis_codes: tuple[str, ...]
    output_stem: str


class UnifiedLvmsFetcher:
    def __init__(
        self,
        *,
        lvms_config_path: Path,
        sensitive_root: Path,
        work_root: Path,
        units_path: Path | None = None,
        backlog_report_path: Path | None = None,
        units: Sequence[Unit] | None = None,
        backlog_reports: Mapping[str, dict] | None = None,
        run_batch: Callable[..., int] = run_report_batch,
        today: Callable[[], date] = date.today,
        sleep: Callable[[float], None] = time.sleep,
        history_from: date = date(2024, 1, 1),
    ) -> None:
        self.lvms_config_path = lvms_config_path
        self.sensitive_root = sensitive_root
        self.work_root = work_root
        self.units_path = units_path
        self.backlog_report_path = backlog_report_path
        self.run_batch = run_batch
        self._today = today
        self._sleep = sleep
        self.history_from = history_from
        self.units = tuple(units) if units is not None else None
        self.backlog_reports = dict(backlog_reports or {})

    def fetch_statistics(
        self,
        unit_keys: Sequence[str] | None = None,
    ) -> Mapping[str, Sequence[tuple[ReportRequest, Path]]]:
        today = self._today()
        result: dict[str, tuple[tuple[ReportRequest, Path], ...]] = {}
        configured = self.units if self.units is not None else load_units(self.units_path)
        by_key = {unit.key: unit for unit in configured}
        if unit_keys is None:
            selected = configured
        else:
            unknown = tuple(key for key in unit_keys if key not in by_key)
            if unknown:
                raise ValueError(
                    "Ukjent statistikkenhet: " + ", ".join(unknown)
                )
            selected = tuple(by_key[key] for key in unit_keys)
        for unit in selected:
            if unit.profile == "lege" and any(r.job_key == "workflow" for r in unit.reports):
                usernames = ()
                self._backfill_flow_months(unit, today)
                planned = [(unit.report_by_key("workflow"), today.replace(day=1), today)]
            elif unit.profile == "lege":
                raise ValueError("Patolog krever et oppdatert workflow-oppsett i JSON.")
            else:
                usernames = ()
                created_from, created_to = plan_window(
                    self.sensitive_root,
                    kind="statistics",
                    unit=unit.key,
                    baseline=date(2024, 1, 1),
                    today=today,
                )
                planned = [(report, created_from, created_to) for report in unit.reports]
            jobs = tuple(
                _statistics_job(unit, report, start, end, usernames=usernames)
                for report, start, end in planned
            )
            if unit.profile == "lege":
                sources = tuple(self._run_jobs((job,), unit.key)[0] for job in jobs)
            else:
                sources = self._run_jobs(jobs, unit.key)
            result[unit.key] = tuple(
                (
                    ReportRequest(
                        kind="statistics",
                        unit=unit.key,
                        report_name=report.report_id,
                        date_from=job.interval.created_from,
                        date_to=job.interval.created_to,
                    ),
                    source,
                )
                for (report, _, _), job, source in zip(planned, jobs, sources, strict=True)
            )
        return result

    def _backfill_flow_months(self, unit: Unit, today: date) -> None:
        from ._statistics import patolog_flow as flow

        folder = StorageLayout(self.sensitive_root).raw_root / "statistics" / unit.key
        existing = flow.latest_months(folder)
        report = unit.report_by_key("workflow")
        month = self.history_from.replace(day=1)
        archive = RawArchive(self.sensitive_root)
        while month < today.replace(day=1):
            end = _month_end(month)
            previous = existing.get(month)
            if previous is None or flow.needs_refresh(previous[0], month, previous[1], today):
                job = _statistics_job(unit, report, month, end)
                source = self._run_jobs((job,), unit.key)[0]
                try:
                    flow.validate_month(source, month, end, laboratory=job.laboratory, processes=job.process_codes)
                except ValueError as exc:
                    raise RunFailure("CSV_INVALID", f"patolog/workflow/{month.isoformat()}") from exc
                archive.store(source, ReportRequest(kind="statistics", unit=unit.key,
                    report_name=report.report_id, date_from=month, date_to=end))
                remove_archived_download(source, self.sensitive_root)
            month = end + timedelta(days=1)

    def fetch_backlog(self, unit_key: str = "hemato", report_path: Path | None = None) -> tuple[ReportRequest, Path]:
        today = self._today()
        payload = self.backlog_reports.get(unit_key)
        if payload is not None:
            definition = report_definition(payload)
        else:
            path = report_path or self.backlog_report_path
            if path is None:
                raise ValueError("Velg et JSON-oppsett for restanse.")
            definition = load_report_definition(path)
        created_from, created_to = BACKLOG_FROM, today
        job = ReportJob(
            job_key="backlog",
            report_type=definition.report_type,
            category=definition.category,
            report_id=definition.report_id,
            report_groups=definition.report_groups,
            analysis_codes=definition.analysis_codes,
            interval=ReportInterval(created_from, created_to),
            output_stem=definition.output_stem,
        )
        source = self._run_jobs((job,), "backlog")[0]
        return (
            ReportRequest(
                kind="backlog",
                unit=unit_key,
                report_name=definition.output_stem,
                date_from=created_from,
                date_to=created_to,
            ),
            source,
        )

    def _run_jobs(self, jobs: tuple[ReportJob, ...], run_label: str) -> tuple[Path, ...]:
        checkpoint_writer_lease()
        run_root = self.work_root / f"{run_label}-{uuid4().hex}"
        run_root.mkdir(parents=True, exist_ok=False)
        jobs_path = _write_jobs(run_root / "jobs.json", jobs)
        for attempt in range(1, 4):
            checkpoint_writer_lease()
            failures: list[RunFailure] = []
            exit_code = self.run_batch(
                self.lvms_config_path, jobs_path,
                tuple(job.job_key for job in jobs), repository_root=run_root,
                error_reporter=failures.append,
            )
            if exit_code == 0:
                checkpoint_writer_lease()
                break
            error = failures[-1] if failures else RunFailure("LVMS_FAILED", "batch")
            error.attempt, error.run_id = attempt, run_root.name
            if not error.retryable or attempt == 3:
                raise error
            self._sleep(2 ** attempt)
        sources = tuple(run_root / "rådata" / batch_filename(job) for job in jobs)
        missing = [source.name for source in sources if not source.is_file()]
        if missing:
            raise RunFailure("DOWNLOAD_INCOMPLETE", "output_check", run_id=run_root.name)
        for job, source in zip(jobs, sources, strict=True):
            if job.laboratory:
                from ._statistics.patolog_flow import validate_month
                try:
                    validate_month(source, job.interval.created_from, job.interval.created_to,
                                   laboratory=job.laboratory, processes=job.process_codes)
                except ValueError as exc:
                    raise RunFailure("CSV_INVALID", "patolog/workflow/download") from exc
        return sources


def _statistics_job(unit: Unit, report, created_from: date, created_to: date, *, usernames: tuple[str, ...] = ()) -> ReportJob:
    return ReportJob(
        job_key=report.job_key,
        report_type="PRODSTAT",
        category="PATOLOGI",
        report_id=report.fetch_report_id,
        report_groups=(),
        analysis_codes=report.analysis_codes or unit.analysis_codes,
        interval=ReportInterval(created_from, created_to),
        output_stem=report.report_id,
        usernames=usernames if report.job_key in {"production", "macro"} else (),
        laboratory=report.laboratory,
        process_codes=report.process_codes,
    )


def _month_end(month: date) -> date:
    next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def _write_jobs(path: Path, jobs: tuple[ReportJob, ...]) -> Path:
    payload = {
        "jobs": [
            {
                "job_key": job.job_key,
                "report_type": job.report_type,
                "category": job.category,
                "report_id": job.report_id,
                "report_groups": list(job.report_groups),
                "analysis_codes": list(job.analysis_codes),
                "usernames": list(job.usernames),
                "laboratory": job.laboratory,
                "process_codes": list(job.process_codes),
                "created_from": job.interval.created_from.strftime("%d.%m.%Y"),
                "created_to": job.interval.created_to.strftime("%d.%m.%Y"),
                "output_stem": job.output_stem,
            }
            for job in jobs
        ]
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_report_definition(path: Path) -> ReportDefinition:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Kunne ikke lese RESTANSE-rapportdefinisjonen.") from exc
    return report_definition(raw)


def report_definition(raw: Mapping[str, object]) -> ReportDefinition:
    try:
        definition = ReportDefinition(
            report_type=str(raw["report_type"]),
            category=str(raw["category"]),
            report_id=str(raw["report_id"]),
            report_groups=tuple(raw["report_groups"]),
            analysis_codes=tuple(raw["analysis_codes"]),
            output_stem=str(raw["output_stem"]),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("RESTANSE-rapportdefinisjonen er ugyldig.") from exc
    if not definition.report_groups or not definition.analysis_codes:
        raise ValueError("RESTANSE-rapporten mangler grupper eller analyser.")
    return definition


def plan_window(
    sensitive_root: Path,
    *,
    kind: str,
    unit: str,
    baseline: date,
    today: date,
) -> tuple[date, date]:
    archive = StorageLayout(sensitive_root).raw_root / kind / unit
    completed: list[date] = []
    if archive.is_dir():
        for path in archive.glob("*.csv"):
            match = _WINDOW.search(path.name)
            if match is not None:
                completed.append(date.fromisoformat(match.group(2)))
    if not completed:
        return baseline, today
    return max(baseline, max(completed) - timedelta(days=2)), today
