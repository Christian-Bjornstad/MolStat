from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import re
from uuid import uuid4

from .lvms.batch_runner import run_report_batch
from .lvms.report import ReportRequest
from .lvms.report_job import ReportInterval, ReportJob, batch_filename
from .statistics import Unit, load_units


_WINDOW = re.compile(
    r"__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})(?:__r\d+)?\.csv$"
)


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
    ) -> None:
        self.lvms_config_path = lvms_config_path
        self.sensitive_root = sensitive_root
        self.work_root = work_root
        self.units_path = units_path
        self.backlog_report_path = backlog_report_path
        self.run_batch = run_batch
        self._today = today

    def fetch_statistics(
        self,
    ) -> Mapping[str, Sequence[tuple[ReportRequest, Path]]]:
        today = self._today()
        result: dict[str, tuple[tuple[ReportRequest, Path], ...]] = {}
        for unit in load_units(self.units_path):
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
                        date_from=created_from,
                        date_to=created_to,
                    ),
                    source,
                )
                for report, source in zip(unit.reports, sources, strict=True)
            )
        return result

    def fetch_backlog(self) -> tuple[ReportRequest, Path]:
        today = self._today()
        definition = load_report_definition(self.backlog_report_path)
        created_from, created_to = plan_window(
            self.sensitive_root,
            kind="backlog",
            unit="hemato",
            baseline=date(2026, 1, 1),
            today=today,
        )
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
                unit="hemato",
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
        exit_code = self.run_batch(
            self.lvms_config_path,
            jobs_path,
            tuple(job.job_key for job in jobs),
            repository_root=run_root,
        )
        if exit_code != 0:
            raise RuntimeError(f"LVMS-kjøringen for {run_label} feilet sikkert.")
        sources = tuple(run_root / "rådata" / batch_filename(job) for job in jobs)
        missing = [source.name for source in sources if not source.is_file()]
        if missing:
            raise RuntimeError(
                f"LVMS-kjøringen mangler {len(missing)} forventede råfiler."
            )
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
