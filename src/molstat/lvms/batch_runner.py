from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit

from molstat.lvms.batch_form import BatchFormError, BatchReportForm
from molstat.lvms.batch_navigation import (
    BatchNavigationError,
    DefinedReportsNavigator,
    DefinedReportsPage,
    discover_defined_reports_page,
)
from molstat.lvms.browser_runtime import BrowserCleanupError, close_owned, open_page
from molstat.lvms.browser_session import open_owned_browser
from molstat.lvms.cdp import (
    BrowserPage,
    CdpConnection,
    CdpNavigationError,
    CdpProtocolError,
    CdpTimeout,
)
from molstat.lvms.config import AppConfig, load_app_config
from molstat.lvms.dom_actions import DocumentDomActions
from molstat.lvms.downloads import (
    CsvArrivalDetector,
    DownloadStatus,
    finalize_csv,
)
from molstat.lvms.report_job import (
    ReportJob,
    batch_filename,
    load_report_jobs,
    select_batch_jobs,
)


@dataclass(frozen=True)
class BatchRunnerDependencies:
    config_load: Callable[[Path, Path], AppConfig]
    jobs_load: Callable[[Path], tuple[ReportJob, ...]]
    browser_open: Callable[[Path], Any]
    connection_open: Callable[[Any], Any]
    page_factory: Callable[[Any], Any]
    actions_factory: Callable[[Any, str], Any]
    navigator_factory: Callable[[str, Callable[[], float], Callable[[float], None]], Any]
    form_factory: Callable[
        [Any, Any, str, Callable[[], float], Callable[[float], None]], Any
    ]
    contract_discover: Callable[[Any, str], DefinedReportsPage | None]
    detector_factory: Callable[[Path], Any]
    finalizer: Callable[[Path, Path, str], Path]
    clock: Callable[[], float]
    sleeper: Callable[[float], None]


def _default_dependencies() -> BatchRunnerDependencies:
    return BatchRunnerDependencies(
        config_load=lambda path, root: load_app_config(path, repository_root=root),
        jobs_load=load_report_jobs,
        browser_open=open_owned_browser,
        connection_open=CdpConnection.open,
        page_factory=BrowserPage,
        actions_factory=DocumentDomActions,
        navigator_factory=lambda origin, clock, sleeper: DefinedReportsNavigator(
            origin, clock=clock, sleep=sleeper
        ),
        form_factory=lambda page, actions, origin, clock, sleeper: BatchReportForm(
            page, actions, origin, clock=clock, sleep=sleeper
        ),
        contract_discover=discover_defined_reports_page,
        detector_factory=CsvArrivalDetector,
        finalizer=finalize_csv,
        clock=time.monotonic,
        sleeper=time.sleep,
    )


def _write_review(stream: TextIO, job: ReportJob) -> None:
    review = job.review()
    stream.write(f"Job: {review.job_key}\n")
    stream.write(f"Report ID: {review.report_id}\n")
    stream.write(f"Analysis count: {review.analysis_count}\n")
    stream.write(f"Interval: {review.created_from} to {review.created_to}\n")


def _write_active_config(
    stream: TextIO, config_path: Path, config: AppConfig
) -> None:
    host = urlsplit(config.landing_url).hostname or "ukjent"
    stream.write(f"Oppsett: {config_path}\n")
    stream.write(f"LVMS-vert: {host}\n")
    stream.write(f"Edge-profil: {config.profile_directory}\n")


def _safe_failure_reason(error: Exception, stage: str) -> str | None:
    if isinstance(error, BatchFormError):
        return f"LVMS-rapportskjemaet kunne ikke fylles ut ({stage})"
    if isinstance(error, BatchNavigationError):
        return f"Fant ikke siden «Definerte rapporter» ({stage})"
    if stage != "lvms_open":
        return None
    if isinstance(error, CdpNavigationError):
        return f"Edge kunne ikke nå LVMS ({error.category})"
    if isinstance(error, CdpTimeout):
        if str(error) == "SSO did not return to the expected origin":
            return (
                "SSO returnerte ikke til LVMS; kontroller innlogging "
                "og Edge-profil"
            )
        return "Tidsavbrudd mens Edge åpnet LVMS"
    if isinstance(error, CdpProtocolError):
        return "Edge avviste navigasjonen til LVMS"
    return None


def _wait_for_page(
    page: Any,
    expected_origin: str,
    dependencies: BatchRunnerDependencies,
    *,
    timeout_seconds: float = 20,
) -> DefinedReportsPage:
    deadline = dependencies.clock() + timeout_seconds
    while dependencies.clock() < deadline:
        contract = dependencies.contract_discover(page, expected_origin)
        if contract is not None:
            return contract
        dependencies.sleeper(0.1)
    raise TimeoutError("Defined Reports page did not become ready")


def _wait_for_csv(
    detector: Any,
    dependencies: BatchRunnerDependencies,
    timeout_seconds: float,
) -> Path:
    deadline = dependencies.clock() + timeout_seconds
    while dependencies.clock() < deadline:
        status = detector.poll()
        if status is DownloadStatus.DETECTED:
            detected = detector.detected_path()
            if not isinstance(detected, Path):
                raise RuntimeError("completed CSV was unavailable")
            return detected
        if status in {DownloadStatus.AMBIGUOUS, DownloadStatus.MISSING}:
            raise RuntimeError("download integrity failed")
        dependencies.sleeper(0.5)
    raise TimeoutError("report download timed out")


def run_report_batch(
    config_path: Path,
    jobs_path: Path,
    job_keys: tuple[str, ...],
    *,
    dependencies: BatchRunnerDependencies | None = None,
    output: TextIO | None = None,
    repository_root: Path | None = None,
    timeout_seconds: float = 600,
    progress: Callable[[int, int], None] | None = None,
    failure: Callable[[str], None] | None = None,
) -> int:
    active = dependencies or _default_dependencies()
    stream = output or sys.stdout
    root = repository_root or Path(__file__).resolve().parents[2]
    edge: Any | None = None
    connection: Any | None = None
    current_job: str | None = None
    current_stage = "configuration"
    result = 2

    def set_stage(stage: str) -> None:
        nonlocal current_stage
        current_stage = stage

    try:
        if not 1 <= timeout_seconds <= 3600:
            raise ValueError("report timeout is invalid")
        config = active.config_load(config_path, root)
        _write_active_config(stream, config_path, config)
        output_directory = (root / "rådata").resolve()
        output_directory.mkdir(parents=True, exist_ok=True)
        set_stage("job_definitions")
        jobs = select_batch_jobs(active.jobs_load(jobs_path), job_keys)
        set_stage("output_check")
        filenames = tuple(batch_filename(job) for job in jobs)
        pending = []
        for job, filename in zip(jobs, filenames, strict=True):
            if (output_directory / filename).exists():
                stream.write(f"Batch job already complete: {job.job_key}.\n")
            else:
                pending.append((job, filename))

        if not pending:
            stream.write("Batch already complete.\n")
            return 0

        for index, (job, filename) in enumerate(pending, start=1):
            current_job = job.job_key
            if progress is not None:
                progress(index, len(pending))
            edge, connection, page = open_page(config, active, stage=set_stage)
            set_stage("download_setup")
            page.configure_downloads(config.download_directory)
            actions = active.actions_factory(page, config.expected_origin)
            navigator = active.navigator_factory(
                config.expected_origin, active.clock, active.sleeper
            )
            set_stage("defined_reports")
            navigator.reach(page, actions, stage=set_stage)
            form = active.form_factory(
                page,
                actions,
                config.expected_origin,
                active.clock,
                active.sleeper,
            )
            set_stage(f"report_{index}_clear")
            contract = _wait_for_page(page, config.expected_origin, active)
            actions.activate(contract.clear)
            form.wait_until_clear()
            set_stage(f"report_{index}_fill")
            contract = _wait_for_page(page, config.expected_origin, active)
            form.populate(contract, job)
            _write_review(stream, job)
            set_stage(f"report_{index}_export")
            contract = _wait_for_page(page, config.expected_origin, active)
            page.configure_downloads(config.download_directory)
            detector = active.detector_factory(config.download_directory)
            detector.start()
            actions.activate(contract.export)
            set_stage(f"report_{index}_download")
            source = _wait_for_csv(detector, active, timeout_seconds)
            active.finalizer(source, output_directory, filename)
            stream.write(f"Batch job completed: {job.job_key} -> {filename}\n")
            set_stage(f"report_{index}_cleanup")
            if close_owned(connection, edge):
                raise BrowserCleanupError("owned browser cleanup did not complete")
            connection = None
            edge = None
        result = 0
    except BrowserCleanupError:
        if failure is not None:
            failure(current_stage)
        stream.write("Batch cleanup did not complete.\n")
        result = 2
    except KeyboardInterrupt:
        stream.write("Batch cancelled.\n")
        result = 130
    except Exception as exc:
        if failure is not None:
            failure(current_stage)
        reason = _safe_failure_reason(exc, current_stage)
        if reason is not None:
            stream.write(f"Årsak: {reason}.\n")
        if current_job is None:
            stream.write("Batch failed safely.\n")
        else:
            stream.write(f"Batch job failed safely: {current_job}.\n")
        result = 2
    finally:
        if close_owned(connection, edge):
            if failure is not None:
                failure("cleanup")
            stream.write("Batch cleanup did not complete.\n")
            result = 2
    return result

