from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import re
import time
from uuid import uuid4

from .archive import RawArchive
from .lvms.batch_runner import run_report_batch
from .lvms.report import ReportRequest
from .lvms.report_job import ReportInterval, ReportJob, batch_filename
from .statistics import Unit, load_units
from .failures import RunFailure


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
        units_path: Path,
        backlog_report_path: Path,
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

    def fetch_statistics(
        self,
        unit_keys: Sequence[str] | None = None,
    ) -> Mapping[str, Sequence[tuple[ReportRequest, Path]]]:
        today = self._today()
        result: dict[str, tuple[tuple[ReportRequest, Path], ...]] = {}
        configured = load_units(self.units_path)
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
            if unit.profile == "lege":
                self._backfill_patolog_months(unit, today)
                windows = monthly_process_windows(today)
                jobs = tuple(
                    _statistics_job(unit, report, *windows[report.job_key])
                    for report in unit.reports
                )
                sources = tuple(self._run_jobs((job,), unit.key)[0] for job in jobs)
            else:
                created_from, created_to = plan_window(
                    self.sensitive_root,
                    kind="statistics",
                    unit=unit.key,
                    baseline=date(2024, 1, 1),
                    today=today,
                )
                jobs = tuple(_statistics_job(unit, report, created_from, created_to) for report in unit.reports)
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
                for report, job, source in zip(unit.reports, jobs, sources, strict=True)
            )
        return result

    def _backfill_patolog_months(self, unit: Unit, today: date) -> None:
        from ._statistics.patolog_process import _latest_by_month, _read

        previous_start, _ = monthly_process_windows(today)["previous"]
        archive_dir = self.sensitive_root / "raw" / "statistics" / unit.key
        completed = set(_latest_by_month(archive_dir)) if archive_dir.is_dir() else set()
        report = unit.report_by_key("previous")
        month = self.history_from.replace(day=1)
        archive = RawArchive(self.sensitive_root)
        while month < previous_start:
            next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
            if month not in completed:
                end = next_month - timedelta(days=1)
                job = _statistics_job(unit, report, month, end)
                source = self._run_jobs((job,), unit.key)[0]
                _read(source)
                archive.store(source, ReportRequest(
                    kind="statistics", unit=unit.key, report_name=report.report_id,
                    date_from=month, date_to=end,
                ))
                source.unlink()
            month = next_month

    def fetch_backlog(self, unit_key: str = "hemato", report_path: Path | None = None) -> tuple[ReportRequest, Path]:
        today = self._today()
        definition = load_report_definition(report_path or self.backlog_report_path)
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
        run_root = self.work_root / f"{run_label}-{uuid4().hex}"
        run_root.mkdir(parents=True, exist_ok=False)
        jobs_path = _write_jobs(run_root / "jobs.json", jobs)
        for attempt in range(1, 4):
            failures: list[RunFailure] = []
            exit_code = self.run_batch(
                self.lvms_config_path, jobs_path,
                tuple(job.job_key for job in jobs), repository_root=run_root,
                error_reporter=failures.append,
            )
            if exit_code == 0:
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
        return sources


def _statistics_job(unit: Unit, report, created_from: date, created_to: date) -> ReportJob:
    return ReportJob(
        job_key=report.job_key,
        report_type="PRODSTAT",
        category="PATOLOGI",
        report_id=report.fetch_report_id,
        report_groups=(),
        analysis_codes=report.analysis_codes or unit.analysis_codes,
        interval=ReportInterval(created_from, created_to),
        output_stem=report.report_id,
    )


def monthly_process_windows(today: date) -> dict[str, tuple[date, date]]:
    current_start = today.replace(day=1)
    previous_end = current_start - timedelta(days=1)
    return {
        "current": (current_start, today),
        "previous": (previous_end.replace(day=1), previous_end),
    }


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
    archive = sensitive_root / "raw" / kind / unit
    completed: list[date] = []
    if archive.is_dir():
        for path in archive.glob("*.csv"):
            match = _WINDOW.search(path.name)
            if match is not None:
                completed.append(date.fromisoformat(match.group(2)))
    if not completed:
        return baseline, today
    return max(baseline, max(completed) - timedelta(days=2)), today
