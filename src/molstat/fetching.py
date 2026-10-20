from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
import codecs
import csv
import hashlib
import json
import os
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
from .failures import RunFailure, storage_failure
from ._writer_lease import checkpoint_writer_lease
from .recovery import check_cancelled, emit_retry, wait_before_retry, retry_operation, uncancellable_cleanup


_WINDOW = re.compile(
    r"__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})(?:__r\d+)?\.csv$"
)
BACKLOG_FROM = date(2024, 1, 1)
REPORT_TIMEOUT_SECONDS = 300
MAX_REPORT_REQUESTS = 24
MAX_SPLIT_DEPTH = 8


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
        check_cancelled()
        checkpoint_writer_lease()
        run_root = self.work_root / f"{run_label}-{uuid4().hex}"
        run_root.mkdir(parents=True, exist_ok=False)
        output = run_root / "rådata"
        output.mkdir()
        sources = []
        for job in jobs:
            check_cancelled()
            parts = self._fetch_report_parts(job, run_root, budget=[0])
            check_cancelled()
            destination = output / batch_filename(job)
            if len(parts) == 1:
                _install_confirmed_report(parts[0], destination)
            else:
                combine_report_parts(parts, destination)
            sources.append(destination)
        for job, source in zip(jobs, sources, strict=True):
            if job.laboratory:
                from ._statistics.patolog_flow import validate_month
                try:
                    validate_month(source, job.interval.created_from, job.interval.created_to,
                                   laboratory=job.laboratory, processes=job.process_codes)
                except ValueError as exc:
                    raise RunFailure("CSV_INVALID", "patolog/workflow/download") from exc
        return tuple(sources)

    def _fetch_report_parts(self, job: ReportJob, run_root: Path, *, budget: list[int],
                            depth: int = 0) -> tuple[Path, ...]:
        for attempt in range(1, 4):
            check_cancelled()
            if budget[0] >= MAX_REPORT_REQUESTS:
                raise RunFailure("LVMS_TIMEOUT", "report_attempt_limit", run_id=run_root.name)
            budget[0] += 1
            checkpoint_writer_lease()
            # A new attempt never trusts an incomplete candidate from an earlier
            # browser session. Confirmed reports are retained by the caller.
            attempt_root = run_root / f"attempt-{uuid4().hex}"
            attempt_root.mkdir()
            jobs_path = _write_jobs(attempt_root / "jobs.json", (job,))
            failures: list[RunFailure] = []
            exit_code = self.run_batch(
                self.lvms_config_path, jobs_path,
                (job.job_key,), repository_root=attempt_root,
                timeout_seconds=REPORT_TIMEOUT_SECONDS, error_reporter=failures.append,
            )
            if exit_code == 0:
                check_cancelled()
                checkpoint_writer_lease()
                source = attempt_root / "rådata" / batch_filename(job)
                if not source.is_file():
                    raise RunFailure("DOWNLOAD_INCOMPLETE", "output_check", run_id=run_root.name)
                if job.laboratory:
                    from ._statistics.patolog_flow import validate_month
                    try:
                        retry_operation(lambda: validate_month(
                            source, job.interval.created_from, job.interval.created_to,
                            laboratory=job.laboratory, processes=job.process_codes),
                            stage="patolog_report_validate")
                    except ValueError as exc:
                        raise RunFailure("CSV_INVALID", "patolog/workflow/download") from exc
                return (source,)
            error = failures[-1] if failures else RunFailure(
                "CANCELLED" if exit_code == 130 else "LVMS_FAILED", "batch")
            error.attempt, error.run_id = attempt, run_root.name
            if not error.retryable:
                raise error
            report_timeout = error.code == "LVMS_TIMEOUT" and error.stage.endswith(("_export", "_download"))
            can_split = (report_timeout and job.interval.created_from < job.interval.created_to
                         and depth < MAX_SPLIT_DEPTH)
            if can_split and attempt == 2:
                check_cancelled()
                emit_retry("lvms_report_split", error, attempt, 3, 0)
                midpoint = job.interval.created_from + (job.interval.created_to - job.interval.created_from) // 2
                left = replace(job, interval=ReportInterval(job.interval.created_from, midpoint))
                right = replace(job, interval=ReportInterval(midpoint + timedelta(days=1), job.interval.created_to))
                return (*self._fetch_report_parts(left, run_root, budget=budget, depth=depth + 1),
                        *self._fetch_report_parts(right, run_root, budget=budget, depth=depth + 1))
            if attempt == 3:
                raise error
            delay = (5.0, 15.0)[attempt - 1]
            emit_retry("lvms_report", error, attempt + 1, 3, delay)
            wait_before_retry(delay, sleep=self._sleep)
        raise AssertionError("Unreachable report attempt state")


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


def combine_report_parts(parts: Sequence[Path], destination: Path) -> None:
    """Join disjoint date windows without changing headers or dropping glass rows."""
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        retry_operation(lambda: _write_combined_parts(parts, temporary), stage="report_split_copy")
    except (csv.Error, UnicodeError) as exc:
        _discard_report_staging(temporary)
        raise RunFailure("CSV_INVALID", "report_split_data") from exc
    except RunFailure as exc:
        if exc.code == "CSV_INVALID":
            _discard_report_staging(temporary)
        raise
    # Keep a completed staging file on an unknown rename/I/O outcome. Never
    # resubmit a report or repeat its import to repair local file delivery.
    _install_confirmed_report(temporary, destination)


def _discard_report_staging(temporary: Path) -> None:
    try:
        temporary.unlink(missing_ok=True)
    except OSError:
        pass


def _report_digest(path: Path) -> str:
    def digest() -> str:
        with path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()
    return retry_operation(digest, stage="report_candidate_hash")


def _install_confirmed_report(source: Path, destination: Path) -> None:
    expected_digest = _report_digest(source)
    def safe_to_retry(error: BaseException) -> bool:
        failure = storage_failure(error)
        if failure is None or failure.code not in {"FILE_ACCESS", "FILE_BUSY"}:
            return False
        try:
            return source.is_file() and not destination.exists()
        except OSError:
            return False
    def install() -> None:
        if destination.exists():
            raise RunFailure("DOWNLOAD_INCOMPLETE", "report_output_conflict")
        try:
            os.replace(source, destination)
        except OSError:
            # A server can commit the rename then lose its response. Confirm
            # those exact bytes before accepting success; an unknown outcome
            # keeps all existing files and is never blindly renamed again.
            try:
                with uncancellable_cleanup():
                    if not source.exists() and destination.is_file() and _report_digest(destination) == expected_digest:
                        return
            except OSError:
                pass
            raise
    retry_operation(install, stage="report_candidate_install", retry_if=safe_to_retry)


def _write_combined_parts(parts: Sequence[Path], temporary: Path) -> None:
    header = None
    encoding = None
    for part in parts:
        check_cancelled()
        with part.open("rb") as source:
            prefix = source.read(3)
        current_encoding = "utf-8-sig" if prefix.startswith(codecs.BOM_UTF8) else "cp1252"
        if encoding is not None and current_encoding != encoding:
            raise RunFailure("CSV_INVALID", "report_split_encoding")
        encoding = current_encoding
        with part.open(encoding=encoding, newline="") as source:
            reader = csv.reader(source, delimiter=";", strict=True)
            current_header = next(reader, None)
            if (not current_header or len(set(current_header)) != len(current_header)
                    or (header is not None and current_header != header)):
                raise RunFailure("CSV_INVALID", "report_split_columns")
            with temporary.open("w" if header is None else "a", encoding=encoding, newline="") as output:
                writer = csv.writer(output, delimiter=";")
                if header is None:
                    header = current_header
                    writer.writerow(header)
                for row in reader:
                    if not row or not any(value.strip() for value in row):
                        continue
                    if len(row) != len(header):
                        raise RunFailure("CSV_INVALID", "report_split_columns")
                    writer.writerow(row)
                output.flush()
                os.fsync(output.fileno())
    if header is None:
        raise RunFailure("CSV_INVALID", "report_split_columns")


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
