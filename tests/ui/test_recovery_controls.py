from types import SimpleNamespace

from molstat.orchestrator import JobResult
from molstat.recovery import recovery_context, retry_operation, check_cancelled
from molstat.ui.app import MainWindow, _JobWorker


def test_worker_exposes_retry_progress_before_finishing(qtbot):
    calls, updates, results = [], [], []
    def run(kind, trigger):
        def operation():
            calls.append(True)
            if len(calls) == 1:
                raise PermissionError('locked')
            return JobResult(kind, 'succeeded', {})
        with recovery_context(sleep=lambda delay: None):
            return retry_operation(operation, stage='excel_replace')
    worker = _JobWorker(SimpleNamespace(run=run), 'excel')
    worker.signals.progress.connect(updates.append)
    worker.signals.finished.connect(results.append)
    worker.run()
    assert len(updates) == 1
    assert 'nytt forsøk 2/5' in str(updates[0])
    assert results[0].status == 'succeeded'


def test_stop_button_signals_running_worker_without_launching_another_job(qtbot):
    window = MainWindow(SimpleNamespace(), None)
    qtbot.addWidget(window)
    worker = _JobWorker(SimpleNamespace(), 'hemato')
    window._workers.add(worker)
    window._refresh_run_button_states()
    assert window.stop_button.isEnabled()
    window.stop_button.click()
    assert worker.cancel.is_set()
    assert not window.stop_button.isEnabled()
    window._workers.clear()


def test_cancelled_worker_returns_cancelled_status_without_crashing(qtbot):
    results = []
    worker = _JobWorker(SimpleNamespace(), 'hemato', operation=check_cancelled)
    worker.signals.finished.connect(results.append)
    worker.cancel.set()
    worker.run()
    assert results[0].status == 'failed'
    assert results[0].error_code == 'CANCELLED'
