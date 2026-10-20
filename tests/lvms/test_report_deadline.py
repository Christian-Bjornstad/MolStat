from dataclasses import replace
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from threading import Event

from molstat.lvms.batch_runner import run_report_batch
from molstat.lvms.downloads import DownloadStatus
from molstat.lvms.cdp import CdpConnection, CdpTimeout
from molstat.lvms.browser_runtime import open_page
from molstat.lvms.browser_session import open_owned_browser
from .test_batch_runner import BatchHarness, JOB_KEYS


def test_export_time_consumes_same_report_deadline_and_timeout_can_retry():
    harness = BatchHarness()
    try:
        now = [0.0]
        active = harness.dependencies()
        factory = active.actions_factory
        def actions_factory(page, origin):
            actions = factory(page, origin)
            activate = actions.activate
            def activate_slow(control):
                activate(control)
                if control.control.element_id == "export":
                    now[0] += 301
            actions.activate = activate_slow
            return actions
        dependencies = replace(active, actions_factory=actions_factory,
                               clock=lambda: now[0], sleeper=lambda seconds: now.__setitem__(0, now[0]+seconds))
        failures = []

        result = run_report_batch(Path("config.json"), Path("jobs.json"), JOB_KEYS,
                                  dependencies=dependencies, timeout_seconds=300,
                                  repository_root=harness.config.profile_directory.parent,
                                  output=io.StringIO(), error_reporter=failures.append)

        assert result == 2
        assert harness.completed == []
        assert failures[-1].code == "LVMS_TIMEOUT"
        assert failures[-1].retryable
        assert harness.events[-2:] == ["close_connection", "close_edge"]
    finally:
        harness.cleanup()


def test_each_report_uses_a_new_owned_download_directory():
    harness = BatchHarness()
    try:
        active = harness.dependencies()
        directories = []
        page_factory = active.page_factory
        def page_with_tracked_downloads(connection):
            page = page_factory(connection)
            configure = page.configure_downloads
            def configure_tracked(directory):
                directories.append(directory)
                configure(directory)
            page.configure_downloads = configure_tracked
            return page
        dependencies = replace(active, page_factory=page_with_tracked_downloads)
        assert run_report_batch(Path("config.json"), Path("jobs.json"), JOB_KEYS,
                                dependencies=dependencies, output=io.StringIO(),
                                repository_root=harness.config.profile_directory.parent) == 0
        assert len(set(directories)) == 3
        assert all(path != harness.config.download_directory and harness.config.download_directory in path.parents
                   for path in directories)
    finally:
        harness.cleanup()


def test_cdp_commands_consume_one_shared_submission_budget():
    now = [0.0]
    timeouts = []
    class Socket:
        def send(self, payload):
            now[0] += 2
        def recv(self):
            return '{"id":1,"result":{}}'
        def settimeout(self, value):
            timeouts.append(value)
    connection = CdpConnection(Socket())
    with patch("molstat.lvms.cdp.time.monotonic", side_effect=lambda: now[0]):
        connection.set_deadline(3)
        assert connection.call("Runtime.evaluate", timeout_seconds=10) == {}
        now[0] = 3
        with pytest.raises(CdpTimeout):
            connection.call("Input.dispatchMouseEvent", timeout_seconds=10)
    assert timeouts == [3, 1]


def test_cancel_during_open_page_closes_owned_browser():
    closed = []
    edge = SimpleNamespace(close=lambda: closed.append("edge"))
    config = SimpleNamespace(profile_directory=Path("profile"))
    dependencies = SimpleNamespace(browser_open=lambda _: SimpleNamespace(edge=edge, target=object()),
                                   connection_open=lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        open_page(config, dependencies)
    assert closed == ["edge"]


def test_cancel_during_target_wait_closes_owned_browser():
    closed = []
    edge = SimpleNamespace(port=49152, close=lambda: closed.append("edge"))
    with pytest.raises(KeyboardInterrupt):
        open_owned_browser(Path("profile"), edge_start=lambda _: edge,
                           target_wait=lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert closed == ["edge"]


def test_temporary_finalizer_failure_retries_move_without_resubmitting_report():
    harness = BatchHarness()
    try:
        active = harness.dependencies()
        calls = []
        def finalizer(source, directory, filename):
            calls.append(filename)
            if len(calls) == 1:
                raise PermissionError(13, "synthetic temporary file lock")
            return active.finalizer(source, directory, filename)
        dependencies = replace(active, finalizer=finalizer)
        assert run_report_batch(Path("config.json"), Path("jobs.json"), JOB_KEYS,
                                dependencies=dependencies, output=io.StringIO(),
                                repository_root=harness.config.profile_directory.parent) == 0
        assert len(calls) == 4
        assert harness.export_counts == dict.fromkeys(JOB_KEYS, 1)
    finally:
        harness.cleanup()


def test_stop_during_download_closes_browser_and_never_exports_next_report():
    from molstat.recovery import recovery_context
    harness = BatchHarness()
    try:
        cancel = Event()
        now = [0.0]
        active = harness.dependencies()
        class Detector:
            def __init__(self, directory):
                pass
            def start(self):
                pass
            def poll(self):
                cancel.set()
                return DownloadStatus.WAITING
        dependencies = replace(active, detector_factory=Detector, clock=lambda: now[0],
                               sleeper=lambda seconds: now.__setitem__(0, now[0]+seconds))
        failures = []
        with recovery_context(cancel=cancel):
            result = run_report_batch(Path("config.json"), Path("jobs.json"), JOB_KEYS,
                                      dependencies=dependencies, output=io.StringIO(),
                                      repository_root=harness.config.profile_directory.parent,
                                      error_reporter=failures.append)
        assert result == 130
        assert failures[-1].code == "CANCELLED"
        assert harness.export_counts[JOB_KEYS[0]] == 1
        assert all(harness.export_counts[key] == 0 for key in JOB_KEYS[1:])
        assert harness.events[-2:] == ["close_connection", "close_edge"]
    finally:
        harness.cleanup()


def test_failed_browser_start_cleanup_stops_new_attempts():
    from molstat.lvms.browser_runtime import BrowserCleanupError
    opened = []
    def start(profile):
        opened.append(profile)
        return SimpleNamespace(port=49152, close=lambda: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(BrowserCleanupError):
        open_owned_browser(Path("profile"), edge_start=start,
                           target_wait=lambda _: (_ for _ in ()).throw(CdpTimeout("synthetic")))
    assert len(opened) == 1


def test_navigation_timeout_is_retryable_after_successful_cleanup():
    from molstat.lvms.batch_navigation import BatchNavigationError
    harness = BatchHarness()
    try:
        active = harness.dependencies()
        class Navigator:
            def reach(self, page, actions, *, stage):
                stage("defined_reports_wait_form")
                raise BatchNavigationError("Defined Reports navigation timed out")
        dependencies = replace(active, navigator_factory=lambda *args: Navigator())
        failures = []
        assert run_report_batch(Path("config.json"), Path("jobs.json"), JOB_KEYS,
                                dependencies=dependencies, output=io.StringIO(),
                                repository_root=harness.config.profile_directory.parent,
                                error_reporter=failures.append) == 2
        assert failures[-1].code == "LVMS_TIMEOUT"
        assert failures[-1].retryable
        assert harness.events[-2:] == ["close_connection", "close_edge"]
    finally:
        harness.cleanup()
