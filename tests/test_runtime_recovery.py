import errno
import pytest

from molstat.database import MolStatDatabase
from molstat.orchestrator import MolStatOrchestrator
from molstat.recovery import recovery_context, retry_operation
from molstat.services import DefaultServices


def test_os_error_diagnostic_is_actionable_and_does_not_expose_paths(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    services = DefaultServices(tmp_path / 'settings.json')
    error = PermissionError(errno.EACCES, 'PRIVATE-PATIENT-PATH')
    error.winerror = 5
    services._record_job_failure('hemato_backlog_run_failed', error)
    message = services.diagnostic_messages()[0]
    assert 'FILE_ACCESS' in message
    assert 'OS_ERROR=5' in message
    assert 'hemato_backlog_run' in message
    assert 'PRIVATE' not in message


def test_gui_configuration_os_error_is_safe_and_specific(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    services = DefaultServices(tmp_path / 'settings.json')
    monkeypatch.setattr(services, '_build_system', lambda **kwargs: (_ for _ in ()).throw(PermissionError(errno.EACCES, 'PRIVATE-PATH')))
    orchestrator, message = services.refresh_gui_runtime()
    assert orchestrator is None
    assert 'FILE_ACCESS' in message
    assert 'PRIVATE' not in message


def test_exhausted_run_reports_file_cause_without_replaying_runner(tmp_path):
    database = MolStatDatabase(tmp_path / 'db.sqlite3')
    database.migrate()
    calls = []
    def run():
        calls.append(True)
        error = PermissionError(errno.EACCES, 'PRIVATE-PATH')
        error.winerror = 32
        raise error
    orchestrator = MolStatOrchestrator(database, {'hemato': run}, owner='synthetic')
    result = orchestrator.run('hemato', 'manual')
    assert calls == [True]
    assert result.status == 'failed'
    assert result.error_code == 'FILE_BUSY'
    assert 'FILE_BUSY' in result.message
    assert 'PRIVATE' not in result.message


def test_error_writing_failed_history_does_not_mask_original_cause(tmp_path, monkeypatch):
    database = MolStatDatabase(tmp_path / 'db.sqlite3')
    database.migrate()
    errors = []
    def run():
        raise PermissionError(errno.EACCES, 'PRIVATE-ORIGINAL')
    orchestrator = MolStatOrchestrator(database, {'hemato': run}, owner='synthetic',
        failure_reporter=lambda stage, error: errors.append(stage))
    monkeypatch.setattr(orchestrator, '_finish_run', lambda *args, **kwargs: (_ for _ in ()).throw(OSError(errno.ENOSPC, 'PRIVATE-SECONDARY')))
    result = orchestrator.run('hemato', 'manual')
    assert result.status == 'failed'
    assert result.error_code == 'FILE_ACCESS'
    assert errors == ['hemato_run_failed', 'hemato_history_write_failed']
    assert 'PRIVATE' not in result.message


def test_retry_events_are_recorded_in_actual_log_folder(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    services = DefaultServices(tmp_path / 'settings.json')
    calls = []
    def operation():
        calls.append(True)
        if len(calls) == 1:
            raise PermissionError(errno.EACCES, 'PRIVATE-PATH')
    with recovery_context(observer=services.record_retry, sleep=lambda delay: None):
        retry_operation(operation, stage='excel_replace')
    message = services.diagnostic_messages()[0]
    assert 'nytt forsøk 2/5' in message
    assert 'excel_replace' in message
    assert 'PRIVATE' not in message
    assert message in (services.diagnostic_log_directory() / 'runtime.log').read_text('utf-8')


def test_status_display_survives_storage_disappearing_between_exists_and_stat(tmp_path, monkeypatch):
    from pathlib import Path
    from molstat.config import MolStatSettings
    services = DefaultServices(tmp_path / 'settings.json')
    services.settings = MolStatSettings(sensitive_root=tmp_path, sharepoint_root=tmp_path / 'public')
    services._settings_exist = True
    (tmp_path / 'Prøvesøk.xlsx').write_bytes(b'synthetic')
    original_stat = Path.stat
    calls = []
    def failing_stat(path, *args, **kwargs):
        if path.name == 'Prøvesøk.xlsx':
            calls.append(True)
            if len(calls) > 1:
                raise PermissionError(errno.EACCES, 'PRIVATE-PATH')
        return original_stat(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', failing_stat)
    result = services.overview_status_fields()
    assert result['excel'][0] == 'Ikke tilgjengelig'
    assert 'PRIVATE' not in str(result)


def test_cancelled_run_releases_lease_and_never_runs_next_job(tmp_path):
    from threading import Event
    from molstat.recovery import check_cancelled
    database = MolStatDatabase(tmp_path / 'db.sqlite3')
    database.migrate()
    cancel = Event()
    def run():
        cancel.set()
        check_cancelled()
    with recovery_context(cancel=cancel):
        result = MolStatOrchestrator(database, {'hemato': run}, owner='synthetic').run('hemato', 'manual')
    assert result.error_code == 'CANCELLED'
    assert database.current_lease_owner() is None


def test_stopping_lease_heartbeat_interrupts_its_retry_wait(tmp_path, monkeypatch):
    from datetime import timedelta
    from threading import Event
    import time
    from molstat._writer_lease import WriterLease
    from molstat import recovery
    database = MolStatDatabase(tmp_path / 'db.sqlite3')
    database.migrate()
    attempted = Event()
    def denied(*args, **kwargs):
        attempted.set()
        raise PermissionError(errno.EACCES, 'PRIVATE-PATH')
    monkeypatch.setattr(database, '_open_writer_connection', denied)
    monkeypatch.setattr(recovery, '_sleep', time.sleep)
    lease = WriterLease(database, 'synthetic', timedelta(milliseconds=90))
    lease.thread.start()
    assert attempted.wait(1)
    lease.stopped.set()
    lease.thread.join(timeout=1)
    assert not lease.thread.is_alive()


def test_release_error_preserves_original_job_failure_and_reports_cleanup(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import sqlite3
    database = MolStatDatabase(tmp_path / 'db.sqlite3')
    database.migrate()
    @contextmanager
    def lease(*args, **kwargs):
        yield
        error = sqlite3.OperationalError('PRIVATE-RELEASE')
        error.sqlite_errorcode = sqlite3.SQLITE_IOERR
        error.sqlite_errorname = 'SQLITE_IOERR'
        raise error
    monkeypatch.setattr(database, 'writer_lease', lease)
    events = []
    def run():
        raise PermissionError(errno.EACCES, 'PRIVATE-ORIGINAL')
    runner = MolStatOrchestrator(database, {'hemato': run}, owner='synthetic',
        failure_reporter=lambda stage, error: events.append(stage))
    result = runner.run('hemato', 'manual')
    assert result.error_code == 'FILE_ACCESS'
    assert events == ['hemato_run_failed', 'hemato_lease_cleanup_failed']
    assert 'PRIVATE' not in result.message


def test_lost_root_is_checked_again_without_creating_replacement_database(tmp_path, monkeypatch):
    from pathlib import Path
    from molstat.config import MolStatSettings
    services = DefaultServices(tmp_path / 'settings.json')
    services.settings = MolStatSettings(sensitive_root=tmp_path / 'private')
    services.settings.sensitive_root.mkdir()
    original_stat = Path.stat
    attempts = []
    def denied_once(path, *args, **kwargs):
        if path == services.settings.sensitive_root:
            attempts.append(True)
            if len(attempts) == 1:
                raise PermissionError(errno.EACCES, 'PRIVATE-PATH')
        return original_stat(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', denied_once)
    database = services._database()
    assert database.schema_version() == 7
    assert len(attempts) >= 2


def test_unavailable_root_is_not_created_as_an_empty_replacement(tmp_path):
    from molstat.config import MolStatSettings
    services = DefaultServices(tmp_path / 'settings.json')
    services.settings = MolStatSettings(sensitive_root=tmp_path / 'missing')
    import pytest
    with pytest.raises((OSError, ValueError)):
        services._database()
    assert not services.settings.sensitive_root.exists()


def test_scheduled_entrypoint_explains_os_error_without_traceback_or_private_payload(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    services = DefaultServices(tmp_path / 'settings.json')
    services._settings_exist = True
    monkeypatch.setattr(services, '_build_system', lambda **kwargs: (_ for _ in ()).throw(PermissionError(errno.EACCES, 'PRIVATE-PATH')))
    assert services.auto() == 2
    output = capsys.readouterr().out
    assert json.loads(output)['error_code'] == 'FILE_ACCESS'
    assert 'PRIVATE' not in output


@pytest.mark.parametrize('partial', [False, True])
def test_release_error_preserves_unit_outcomes_from_composite_runner(tmp_path, monkeypatch, partial):
    from contextlib import contextmanager
    import sqlite3
    from molstat.system import CapabilityRun
    database = MolStatDatabase(tmp_path / 'db.sqlite3')
    database.migrate()
    @contextmanager
    def lease(*args, **kwargs):
        yield
        error = sqlite3.OperationalError('PRIVATE-RELEASE')
        error.sqlite_errorcode = sqlite3.SQLITE_IOERR
        error.sqlite_errorname = 'SQLITE_IOERR'
        raise error
    monkeypatch.setattr(database, 'writer_lease', lease)
    outcomes = (CapabilityRun('hemato', 'backlog', {}, PermissionError(errno.EACCES, 'PRIVATE-ORIGINAL')),)
    if partial:
        outcomes += (CapabilityRun('solide', 'backlog', {'rows': 2}),)
    runner = MolStatOrchestrator(database, {'all': lambda: outcomes}, owner='synthetic')
    result = runner.run('all', 'manual')
    assert result.status == ('partial' if partial else 'failed')
    assert result.capability_results[0].error_code == 'FILE_ACCESS'
    assert len(result.capability_results) == len(outcomes)
