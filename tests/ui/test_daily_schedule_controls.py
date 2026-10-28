from datetime import datetime, timedelta, timezone

from molstat.orchestrator import JobResult
from molstat.ui.app import MainWindow
from PyQt6.QtCore import QTime


MORNING = datetime(2026, 10, 28, 7, tzinfo=timezone(timedelta(hours=1)))


class DailyOrchestrator:
    def __init__(self, results=None):
        self.calls = []
        self.results = iter(results or [JobResult("all", "succeeded", {})] * 3)

    def run_daily(self):
        self.calls.append("daily")
        return next(self.results)


def test_open_window_runs_daily_on_timer_and_again_next_day(qtbot):
    orchestrator = DailyOrchestrator()
    window = MainWindow(orchestrator, None)
    qtbot.addWidget(window)
    clock = [MORNING - timedelta(seconds=1)]
    window._schedule_now = lambda: clock[0]
    window._schedule_timer.timeout.emit()
    assert orchestrator.calls == []
    clock[0] = MORNING
    window.showMinimized()
    window._schedule_timer.timeout.emit()
    qtbot.waitUntil(lambda: not window._workers)
    assert orchestrator.calls == ["daily"]
    window._schedule_timer.timeout.emit()
    assert orchestrator.calls == ["daily"]
    clock[0] += timedelta(days=1, hours=2)
    window._schedule_timer.timeout.emit()
    qtbot.waitUntil(lambda: not window._workers)
    assert orchestrator.calls == ["daily", "daily"]
    assert window._schedule_timer.isActive()
    assert window._schedule_timer.interval() == 30_000


def test_startup_check_runs_without_user_action_and_close_stops_timer(qtbot):
    orchestrator = DailyOrchestrator([None])
    window = MainWindow(orchestrator, None)
    qtbot.addWidget(window)
    window._schedule_now = lambda: MORNING.replace(hour=11)
    qtbot.waitUntil(lambda: bool(orchestrator.calls) and not window._workers)
    assert orchestrator.calls == ["daily"]
    window.close()
    assert not window._schedule_timer.isActive()


def test_busy_schedule_retries_but_finished_failure_does_not_loop(qtbot):
    orchestrator = DailyOrchestrator([
        JobResult("all", "busy", {}), JobResult("all", "failed", {})])
    window = MainWindow(orchestrator, None)
    qtbot.addWidget(window)
    window._schedule_now = lambda: MORNING.replace(hour=12)
    for _ in range(3):
        window._check_daily_schedule()
        qtbot.waitUntil(lambda: not window._workers)
    assert orchestrator.calls == ["daily", "daily"]
    assert "feilet" in window.overview.schedule_status.text().casefold()


def test_daily_check_waits_for_manual_work_and_requires_ready_runtime(qtbot):
    orchestrator = DailyOrchestrator()
    window = MainWindow(orchestrator, None)
    qtbot.addWidget(window)
    window._schedule_now = lambda: MORNING
    marker = object()
    window._workers.add(marker)
    window._check_daily_schedule()
    assert orchestrator.calls == []
    window._workers.clear()
    window.orchestrator = None
    window._check_daily_schedule()
    assert orchestrator.calls == []
    window.orchestrator = orchestrator
    window._check_daily_schedule()
    qtbot.waitUntil(lambda: not window._workers)
    assert orchestrator.calls == ["daily"]


def test_already_recorded_day_does_not_claim_new_publication(qtbot):
    window = MainWindow(DailyOrchestrator([None]), None)
    qtbot.addWidget(window)
    window._schedule_now = lambda: MORNING
    window.overview.cards["sharepoint"].set_status("Venter", "Ikke publisert")
    window._check_daily_schedule()
    qtbot.waitUntil(lambda: not window._workers)
    assert window.overview.cards["sharepoint"].state_label.text() == "Venter"
    assert "registrert" in window.overview.schedule_status.text()


def test_editable_schedule_uses_only_saved_time_and_applies_without_restart(qtbot):
    class TimeStore:
        values = {"daily_time": "08:35"}

        def load_settings_fields(self):
            return dict(self.values)

        def save_settings_fields(self, values):
            self.values = dict(values)

    store = TimeStore()
    orchestrator = DailyOrchestrator()
    window = MainWindow(orchestrator, store)
    qtbot.addWidget(window)
    window._schedule_now = lambda: MORNING.replace(hour=8, minute=34)
    assert window.settings_page.daily_time.time() == QTime(8, 35)
    assert "08:35" in window.overview.schedule_status.text()
    window.settings_page.daily_time.setTime(QTime(8, 10))
    window._check_daily_schedule()
    assert orchestrator.calls == []
    window._save_settings()
    assert store.values["daily_time"] == "08:10"
    window._check_daily_schedule()
    qtbot.waitUntil(lambda: not window._workers)
    assert orchestrator.calls == ["daily"]
    assert "08:10" in window.overview.schedule_status.text()


def test_new_saved_time_runs_again_even_after_earlier_automatic_run(qtbot):
    class TimeStore:
        values = {"daily_time": "07:00"}

        def load_settings_fields(self):
            return dict(self.values)

        def save_settings_fields(self, values):
            self.values = dict(values)

    orchestrator = DailyOrchestrator()
    window = MainWindow(orchestrator, TimeStore())
    qtbot.addWidget(window)
    clock = [MORNING]
    window._schedule_now = lambda: clock[0]
    window._check_daily_schedule()
    qtbot.waitUntil(lambda: not window._workers)
    assert orchestrator.calls == ["daily"]
    window.settings_page.daily_time.setTime(QTime(7, 5))
    window._save_settings()
    clock[0] += timedelta(minutes=4)
    window._check_daily_schedule()
    assert orchestrator.calls == ["daily"]
    clock[0] += timedelta(minutes=1)
    window._check_daily_schedule()
    qtbot.waitUntil(lambda: not window._workers)
    assert orchestrator.calls == ["daily", "daily"]
    window._check_daily_schedule()
    assert orchestrator.calls == ["daily", "daily"]
