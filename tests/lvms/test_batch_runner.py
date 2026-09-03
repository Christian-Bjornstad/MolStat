from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from molstat.lvms.batch_controls import DocumentControlIdentity
from molstat.lvms.batch_navigation import DefinedReportsPage
from molstat.lvms.batch_runner import BatchRunnerDependencies, run_report_batch
from molstat.lvms.config import AppConfig
from molstat.lvms.downloads import DownloadError, DownloadStatus
from molstat.lvms.report_job import ReportJob, batch_filename, validate_report_job
from molstat.lvms.control_identity import ControlIdentity


EXPECTED_ORIGIN = "https://lvms.example.invalid"
JOB_KEYS = ("ordered", "answered", "extraction")


def document(
    frame: str, tag: str, element_id: str, **values: str
) -> DocumentControlIdentity:
    return DocumentControlIdentity(
        frame,
        ControlIdentity(tag, element_id=element_id, **values),
    )


def page_contract() -> DefinedReportsPage:
    return DefinedReportsPage(
        document(
            "top", "SELECT", "jobtypeselector", name="jobtypeselector"
        ),
        document(
            "_nav_frame1",
            "BUTTON",
            "clear",
            name="menu",
            control_type="button",
        ),
        document(
            "_nav_frame1",
            "BUTTON",
            "export",
            name="menu",
            control_type="button",
        ),
    )


def report_job(key: str) -> ReportJob:
    return validate_report_job(
        {
            "job_key": key,
            "report_type": "TYPE_A",
            "category": "CATEGORY_A",
            "report_id": f"REPORT-{key.upper()}",
            "analysis_codes": [f"ANALYSIS-{key.upper()}"],
            "created_from": "01.08.2026",
            "created_to": "07.08.2026",
            "output_stem": key,
        }
    )


class BatchHarness:
    def __init__(self, failure_stage: str | None = None, failed_job: str = "answered") -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name).resolve()
        self.config = AppConfig(
            f"{EXPECTED_ORIGIN}/",
            EXPECTED_ORIGIN,
            root / "profile",
            root / "downloads",
        )
        self.failure_stage = failure_stage
        self.failed_job = failed_job
        self.events: list[str] = []
        self.current_job: str | None = None
        self.clear_index = 0
        self.export_counts = {key: 0 for key in JOB_KEYS}
        self.completed: list[str] = []
        self.browser_open_count = 0
        self.download_setup_count = 0

    def cleanup(self) -> None:
        self.temporary.cleanup()

    def dependencies(self) -> BatchRunnerDependencies:
        harness = self

        class Edge:
            def close(self) -> None:
                harness.events.append("close_edge")

        class Connection:
            def close(self) -> None:
                harness.events.append("close_connection")
                if harness.failure_stage in {"cleanup", "open_cleanup"}:
                    raise RuntimeError("synthetic cleanup failure")

        class Page:
            def navigate(
                self, url: str, origin: str, *, timeout_seconds: float
            ) -> object:
                del url, origin, timeout_seconds
                harness.events.append("navigate")
                if harness.failure_stage == "open_cleanup":
                    raise RuntimeError("synthetic navigation failure")
                return object()

            def configure_downloads(self, directory: Path) -> None:
                directory.mkdir(parents=True, exist_ok=True)
                harness.download_setup_count += 1

            def current_origin(self) -> str:
                return EXPECTED_ORIGIN

        class Actions:
            def activate(self, identity: DocumentControlIdentity) -> None:
                if identity.control.element_id == "clear":
                    previous_clear = (
                        harness.events[-1].removeprefix("clear:")
                        if harness.events and harness.events[-1].startswith("clear:")
                        else None
                    )
                    if previous_clear is not None and previous_clear == harness.current_job:
                        key = previous_clear
                    else:
                        key = JOB_KEYS[harness.clear_index]
                        harness.clear_index += 1
                    harness.current_job = key
                    harness.events.append(f"clear:{key}")
                    if harness.failure_stage == "clear" and key == harness.failed_job:
                        raise RuntimeError("synthetic clear failure")
                    return
                if identity.control.element_id == "export":
                    key = harness.current_job
                    assert key is not None
                    harness.export_counts[key] += 1
                    harness.events.append(f"export:{key}")
                    return
                raise AssertionError("unexpected action")

        class Navigator:
            def reach(
                self,
                page: object,
                actions: object,
                *,
                stage: object,
            ) -> DefinedReportsPage:
                del page, actions
                stage("defined_reports_ready")  # type: ignore[operator]
                return page_contract()

        class Form:
            def wait_until_clear(self) -> None:
                key = harness.current_job
                if harness.failure_stage == "clear_wait" and key == harness.failed_job:
                    raise RuntimeError("synthetic clear wait failure")

            def populate(self, contract: DefinedReportsPage, job: ReportJob) -> None:
                del contract
                harness.current_job = job.job_key
                harness.events.append(f"populate:{job.job_key}")
                if harness.failure_stage == "populate" and job.job_key == harness.failed_job:
                    raise RuntimeError("synthetic populate failure")
                if harness.failure_stage == "cancel" and job.job_key == harness.failed_job:
                    raise KeyboardInterrupt

        class Detector:
            def __init__(self, directory: Path) -> None:
                self.directory = directory
                self.key = harness.current_job

            def start(self) -> None:
                return None

            def poll(self) -> DownloadStatus:
                if (
                    harness.failure_stage == "download_ambiguous"
                    and self.key == harness.failed_job
                ):
                    return DownloadStatus.AMBIGUOUS
                return DownloadStatus.DETECTED

            def detected_path(self) -> Path | None:
                assert self.key is not None
                return self.directory / f"generated-{self.key}.csv"

        def browser_open(profile: Path) -> object:
            del profile
            harness.browser_open_count += 1
            if harness.failure_stage == "edge_start":
                raise RuntimeError("synthetic browser startup detail")
            return SimpleNamespace(edge=Edge(), target=object())

        def finalizer(source: Path, directory: Path, filename: str) -> Path:
            del source
            key = harness.current_job
            assert key is not None
            if harness.failure_stage == "duplicate_target" and key == harness.failed_job:
                raise DownloadError("CSV finalization target is invalid")
            harness.events.append(f"finalize:{key}")
            harness.completed.append(key)
            return directory / filename

        return BatchRunnerDependencies(
            config_load=lambda path, root: self.config,
            jobs_load=lambda path: tuple(report_job(key) for key in JOB_KEYS),
            browser_open=browser_open,
            connection_open=lambda target: Connection(),
            page_factory=lambda connection: Page(),
            actions_factory=lambda page, origin: Actions(),
            navigator_factory=lambda origin, clock, sleeper: Navigator(),
            form_factory=lambda page, actions, origin, clock, sleeper: Form(),
            contract_discover=lambda page, origin: page_contract(),
            detector_factory=Detector,
            finalizer=finalizer,
            clock=lambda: 0.0,
            sleeper=lambda seconds: None,
        )


class BatchRunnerTests(unittest.TestCase):
    def run_harness(self, harness: BatchHarness, *, timeout_seconds: float = 600) -> tuple[int, str]:
        self.addCleanup(harness.cleanup)
        output = io.StringIO()
        result = run_report_batch(
            Path("config.json"),
            Path("jobs.json"),
            JOB_KEYS,
            dependencies=harness.dependencies(),
            output=output,
            timeout_seconds=timeout_seconds,
            repository_root=harness.config.profile_directory.parent,
        )
        return result, output.getvalue()

    def test_runs_three_jobs_without_prompt_and_finalizes_each_csv(self) -> None:
        harness = BatchHarness()

        result, output = self.run_harness(harness)

        self.assertEqual(result, 0)
        self.assertEqual(
            harness.events,
            [
                "navigate",
                "clear:ordered",
                "populate:ordered",
                "export:ordered",
                "finalize:ordered",
                "close_connection",
                "close_edge",
                "navigate",
                "clear:answered",
                "populate:answered",
                "export:answered",
                "finalize:answered",
                "close_connection",
                "close_edge",
                "navigate",
                "clear:extraction",
                "populate:extraction",
                "export:extraction",
                "finalize:extraction",
                "close_connection",
                "close_edge",
            ],
        )
        self.assertNotIn("ANALYSIS-ORDERED", output)
        self.assertNotIn(str(harness.config.download_directory), output)
        self.assertEqual(harness.download_setup_count, 6)
        self.assertTrue(
            (harness.config.profile_directory.parent / "rådata").is_dir()
        )

    def test_resumes_batch_by_skipping_existing_completed_report(self) -> None:
        harness = BatchHarness()
        output_directory = harness.config.profile_directory.parent / "rådata"
        output_directory.mkdir(parents=True, exist_ok=True)
        first_job = report_job("ordered")
        (output_directory / batch_filename(first_job)).write_text("existing")

        result, output = self.run_harness(harness)

        self.assertEqual(result, 0)
        self.assertNotIn("populate:ordered", harness.events)
        self.assertEqual(harness.completed, ["answered", "extraction"])
        self.assertIn("Batch job already complete: ordered.", output)

    def test_reports_numeric_progress_without_job_or_report_details(self) -> None:
        harness = BatchHarness()
        self.addCleanup(harness.cleanup)
        progress: list[tuple[int, int]] = []

        result = run_report_batch(
            Path("config.json"),
            Path("jobs.json"),
            JOB_KEYS,
            dependencies=harness.dependencies(),
            output=io.StringIO(),
            progress=lambda current, total: progress.append((current, total)),
            repository_root=harness.config.profile_directory.parent,
        )

        self.assertEqual(result, 0)
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])

    def test_stops_on_first_job_failure_without_export_retry(self) -> None:
        for stage in (
            "clear",
            "clear_wait",
            "populate",
            "download_ambiguous",
            "duplicate_target",
        ):
            with self.subTest(stage=stage):
                harness = BatchHarness(stage)
                result, _ = self.run_harness(harness)

                self.assertEqual(result, 2)
                self.assertLessEqual(harness.export_counts["answered"], 1)
                self.assertEqual(harness.export_counts["extraction"], 0)
                self.assertEqual(harness.completed, ["ordered"])

    def test_cleanup_failure_stops_before_opening_the_next_report(self) -> None:
        harness = BatchHarness("cleanup")

        result, output = self.run_harness(harness)

        self.assertEqual(result, 2)
        self.assertEqual(harness.completed, ["ordered"])
        self.assertIn("cleanup", output.lower())
        self.assertEqual(harness.events[-2:], ["close_connection", "close_edge"])

    def test_cancellation_returns_130_and_preserves_earlier_file(self) -> None:
        harness = BatchHarness("cancel")

        result, _ = self.run_harness(harness)

        self.assertEqual(result, 130)
        self.assertEqual(harness.completed, ["ordered"])
        self.assertEqual(harness.export_counts["answered"], 0)

    def test_invalid_timeout_fails_before_edge_launch(self) -> None:
        for timeout in (0, 6001):
            with self.subTest(timeout=timeout):
                harness = BatchHarness()
                self.addCleanup(harness.cleanup)
                result = run_report_batch(
                    Path("config.json"),
                    Path("jobs.json"),
                    JOB_KEYS,
                    dependencies=harness.dependencies(),
                    output=io.StringIO(),
                    timeout_seconds=timeout,
                    repository_root=harness.config.profile_directory.parent,
                )
                self.assertEqual(result, 2)
                self.assertEqual(harness.browser_open_count, 0)

    def test_single_job_key_batch_completes_without_edge(self) -> None:
        harness = BatchHarness()
        self.addCleanup(harness.cleanup)
        result = run_report_batch(
            Path("config.json"),
            Path("jobs.json"),
            ("ordered",),
            dependencies=harness.dependencies(),
            output=io.StringIO(),
            repository_root=harness.config.profile_directory.parent,
        )
        self.assertEqual(result, 0)

    def test_open_failure_reports_cleanup_incomplete_without_internal_detail(self) -> None:
        harness = BatchHarness("open_cleanup")

        result, output = self.run_harness(harness)

        self.assertEqual(result, 2)
        self.assertIn("cleanup", output.lower())
        self.assertNotIn("synthetic", output.lower())
        self.assertEqual(harness.events, ["navigate", "close_connection", "close_edge"])

    def test_reports_sanitized_edge_start_failure_stage(self) -> None:
        harness = BatchHarness("edge_start")
        self.addCleanup(harness.cleanup)
        failures: list[str] = []

        result = run_report_batch(
            Path("config.json"),
            Path("jobs.json"),
            JOB_KEYS,
            dependencies=harness.dependencies(),
            output=io.StringIO(),
            failure=failures.append,
            repository_root=harness.config.profile_directory.parent,
        )

        self.assertEqual(result, 2)
        self.assertEqual(failures, ["edge_start"])


if __name__ == "__main__":
    unittest.main()

