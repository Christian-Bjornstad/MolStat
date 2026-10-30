from datetime import date
from pathlib import Path
from threading import Event

from molstat.orchestrator import CapabilityResult, JobResult
from molstat.ui.app import MainWindow


class Store:
    def load_settings_fields(self):
        return {"enabled_hemato": "true", "enabled_solide": "true", "enabled_flow": "false",
                "enabled_fish": "false", "enabled_pre": "false", "enabled_lege": "false"}


class Mixed:
    def run(self, target, trigger):
        return JobResult(target, "partial", {"succeeded": 2, "failed": 1}, capability_results=(
            CapabilityResult("hemato", "statistics", "succeeded", {"rows": 10}),
            CapabilityResult("hemato", "backlog", "failed", {}, "Kontroller CSV-formatet", "CSV_INVALID"),
            CapabilityResult("solide", "statistics", "succeeded", {"rows": 8}),
        ))


def test_composite_error_is_shown_only_on_affected_unit_and_capability(qtbot):
    window = MainWindow(Mixed(), Store())
    qtbot.addWidget(window)
    window._start_job("all")
    qtbot.waitUntil(lambda: not window._workers)

    assert "Fullført" in window.overview.unit_cards["solide"].status_label.text()
    hemato = window.overview.unit_cards["hemato"]
    assert "Delvis feil" in hemato.status_label.text()
    assert "Fullført" in hemato.capability_status_labels["statistics"].text()
    assert "Feilet" in hemato.capability_status_labels["backlog"].text()
    assert "Deaktivert" in window.overview.unit_cards["flow"].status_label.text()


def test_global_failure_without_unit_results_does_not_claim_every_unit_failed(qtbot):
    class GlobalFailure:
        def run(self, target, trigger):
            return JobResult(target, "failed", {})
    window = MainWindow(GlobalFailure(), Store())
    qtbot.addWidget(window)
    before = {key: card.status_label.text() for key, card in window.overview.unit_cards.items()}
    window._start_job("all")
    qtbot.waitUntil(lambda: not window._workers)
    assert {key: card.status_label.text() for key, card in window.overview.unit_cards.items()} == before
    assert "feilet" in window.statusBar().currentMessage().lower()


def test_per_unit_settings_shortcut_selects_correct_editor(qtbot):
    window = MainWindow(Mixed(), Store())
    qtbot.addWidget(window)
    window.overview.unit_cards["solide"].settings_button.click()
    assert window.stack.currentWidget() is window.settings_page
    assert window.settings_page.unit_stack.currentWidget().objectName() == "unit-settings-solide"


def test_manual_import_runs_off_thread_and_restores_controls(qtbot, tmp_path):
    class ManualStore(Store):
        def manual_import_available_jobs(self, unit):
            return ("statistics",)
        def manual_import_roles(self, unit, kind):
            return ("antall", "resultater", "ekstraksjon")
        def manual_import(self, plan):
            self.plan = plan
            return JobResult(plan.unit_key, "succeeded", {"rows": 2}, capability_results=(
                CapabilityResult(plan.unit_key, "statistics", "succeeded", {"rows": 2}),
            ))
    store = ManualStore()
    window = MainWindow(Mixed(), store)
    qtbot.addWidget(window)
    window.overview.import_button.click()
    assert window.stack.currentWidget() is window.import_page
    for role, field in window.import_page.file_fields.items():
        source = tmp_path / f"{role}.csv"
        source.write_text("synthetic CSV")
        field.setText(str(source))
    window.import_page.import_button.click()
    qtbot.waitUntil(lambda: not window._workers)
    assert store.plan.unit_key == "hemato"
    assert window.settings_page.isEnabled()
    assert "Fullført" in window.overview.unit_cards["hemato"].status_label.text()


def test_closing_window_waits_for_active_worker(qtbot):
    started, finish = Event(), Event()
    class Running:
        def run(self, target, trigger):
            started.set()
            finish.wait(2)
            return JobResult(target, "succeeded", {"rows": 1})
    window = MainWindow(Running(), Store())
    qtbot.addWidget(window)
    window.show()
    window._start_job("hemato")
    qtbot.waitUntil(started.is_set)
    try:
        assert not window.close()
        assert window.isVisible()
        assert "før appen lukkes" in window.statusBar().currentMessage()
        assert "Importerer" not in window.import_page.import_button.text()
    finally:
        finish.set()
        qtbot.waitUntil(lambda: not window._workers)
    assert window.close()


def test_publication_retry_keeps_failed_source_import_visible(qtbot):
    class Retry:
        def run(self, target, trigger):
            if target == "publish":
                return JobResult(target, "succeeded", {"published": 1}, capability_results=(
                    CapabilityResult("hemato", "statistics", "succeeded", {"published": 1}),
                ))
            return JobResult(target, "failed", {}, capability_results=(
                CapabilityResult("hemato", "statistics", "failed", {}, "Kontroller LVMS"),
            ))
    window = MainWindow(Retry(), Store())
    qtbot.addWidget(window)
    window._start_job("hemato")
    qtbot.waitUntil(lambda: not window._workers)
    assert "Feilet" in window.overview.unit_cards["hemato"].status_label.text()
    window._start_job("publish")
    qtbot.waitUntil(lambda: not window._workers)
    assert "Feilet" in window.overview.unit_cards["hemato"].status_label.text()
    assert window.overview.cards["sharepoint"].state_label.text() == "Publisert"


def test_live_progress_reports_finished_unit_while_next_unit_is_running(qtbot):
    from molstat.progress import emit_progress, plan_progress
    next_started, finish = Event(), Event()
    class Running:
        def run(self, target, trigger):
            plan_progress(2)
            emit_progress('hemato', 'statistics', 'started')
            emit_progress('hemato', 'statistics', 'processing')
            emit_progress('hemato', 'statistics', 'finished')
            emit_progress('solide', 'statistics', 'started')
            emit_progress('solide', 'statistics', 'processing')
            next_started.set()
            finish.wait(3)
            emit_progress('solide', 'statistics', 'finished')
            return JobResult(target, 'succeeded', {'capabilities': 2}, capability_results=(
                CapabilityResult('hemato', 'statistics', 'succeeded', {'rows': 3}),
                CapabilityResult('solide', 'statistics', 'succeeded', {'rows': 4}),
            ))
    window = MainWindow(Running(), Store())
    qtbot.addWidget(window)
    window._start_job('all')
    try:
        qtbot.waitUntil(lambda: next_started.is_set() and 'Behandler' in window.overview.unit_cards['solide'].status_label.text())
        assert 'Fullført' in window.overview.unit_cards['hemato'].status_label.text()
        assert window.overview.run_progress.maximum() == 2
        assert window.overview.run_progress.value() == 1
        assert 'Solide' in window.overview.run_detail.text()
        assert window.overview.run_all.isEnabled() is False
    finally:
        finish.set()
        qtbot.waitUntil(lambda: not window._workers)
    assert window.overview.run_progress.value() == 2
    assert 'Fullført' in window.overview.run_detail.text()
