import errno
import sqlite3

import pytest

from molstat.failures import RunFailure, os_failure
from molstat.recovery import recovery_context, retry_operation, is_transient_storage


def test_transient_step_retries_with_visible_bounded_delays():
    calls, waits, events = [], [], []
    def operation():
        calls.append(True)
        if len(calls) < 3:
            raise PermissionError(errno.EACCES, 'PRIVATE-PATIENT-PATH')
        return 'complete'
    with recovery_context(observer=events.append, sleep=waits.append):
        assert retry_operation(operation, stage='excel_replace') == 'complete'
    assert len(calls) == 3
    assert waits == [5.0, 15.0]
    assert [event.attempt for event in events] == [2, 3]
    assert all(event.max_attempts == 5 and event.code == 'FILE_ACCESS' for event in events)
    assert all('PRIVATE' not in str(event) for event in events)
    assert 'excel_replace' in str(events[0])


def test_exhaustion_preserves_original_error_and_never_loops_forever():
    error = PermissionError(errno.EACCES, 'PRIVATE-PATH')
    calls, waits = [], []
    def operation():
        calls.append(True)
        raise error
    with recovery_context(sleep=waits.append):
        with pytest.raises(PermissionError) as failure:
            retry_operation(operation, stage='archive_copy', delays=(1, 2))
    assert failure.value is error
    assert len(calls) == 3
    assert waits == [1, 2]


@pytest.mark.parametrize('error', [ValueError('PRIVATE'), OSError(errno.ENOSPC, 'PRIVATE'),
                                 FileNotFoundError(errno.ENOENT, 'PRIVATE'), RunFailure('CSV_INVALID', 'csv_import')])
def test_permanent_errors_are_not_retried(error):
    waits = []
    with recovery_context(sleep=waits.append):
        with pytest.raises(type(error)):
            retry_operation(lambda: (_ for _ in ()).throw(error), stage='file_read')
    assert waits == []


def test_wrapped_file_error_is_recognised_without_exposing_payload():
    try:
        raise PermissionError(errno.EACCES, 'PRIVATE')
    except PermissionError as cause:
        try:
            raise RuntimeError('PRIVATE-WRAPPER') from cause
        except RuntimeError as wrapped:
            assert is_transient_storage(wrapped)


def test_retry_observer_failure_does_not_change_operation_result():
    calls = []
    def operation():
        calls.append(True)
        if len(calls) == 1:
            raise PermissionError('locked')
        return 7
    with recovery_context(observer=lambda event: (_ for _ in ()).throw(OSError('log denied')), sleep=lambda delay: None):
        assert retry_operation(operation, stage='database_open') == 7


def test_nested_context_preserves_parent_observer_and_restores_sleeper():
    events, parent_waits, inner_waits = [], [], []
    def fail_once():
        count = []
        def operation():
            count.append(1)
            if len(count) == 1:
                raise PermissionError('locked')
        return operation
    with recovery_context(observer=events.append, sleep=parent_waits.append):
        with recovery_context(sleep=inner_waits.append):
            retry_operation(fail_once(), stage='excel_replace', delays=(1,))
        retry_operation(fail_once(), stage='excel_replace', delays=(2,))
    assert parent_waits == [2]
    assert inner_waits == [1]
    assert len(events) == 2


def test_sqlite_retry_classification_uses_codes_and_excludes_unknown_commit_errors():
    error = sqlite3.OperationalError('PRIVATE')
    for code in [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_READONLY, sqlite3.SQLITE_CANTOPEN]:
        error.sqlite_errorcode = code
        assert is_transient_storage(error)
    for code in [sqlite3.SQLITE_FULL, sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_IOERR]:
        error.sqlite_errorcode = code
        assert not is_transient_storage(error)


@pytest.mark.parametrize(('error_number', 'winerror', 'code', 'retryable'), [
    (errno.EACCES, 5, 'FILE_ACCESS', True), (errno.EACCES, 32, 'FILE_BUSY', True),
    (errno.EIO, 53, 'FILE_UNAVAILABLE', True), (errno.EIO, None, 'FILE_IO', True),
    (errno.ENOSPC, 112, 'FILE_FULL', False), (errno.ENOENT, None, 'FILE_MISSING', False),
    (errno.EINVAL, None, 'FILE_ERROR', False),
])
def test_os_diagnostics_explain_operation_and_safe_numeric_cause(error_number, winerror, code, retryable):
    error = OSError(error_number, 'PRIVATE-PATIENT-PATH')
    if winerror is not None:
        error.winerror = winerror
    failure = os_failure(error, stage='archive_copy')
    assert failure.code == code
    assert failure.retryable is retryable
    assert failure.stage == 'archive_copy'
    assert 'PRIVATE' not in str(failure)
    assert f'OS_ERROR={winerror or error_number}' in failure.detail


def test_os_diagnostics_reject_external_stage_and_codes():
    error = OSError('PRIVATE')
    error.winerror = 'PRIVATE'
    assert 'PRIVATE' not in str(os_failure(error, stage='C:/PRIVATE/PATIENT.csv'))


def test_cancel_stops_waiting_and_prevents_the_next_operation():
    from threading import Event
    from molstat.recovery import wait_before_retry
    cancel = Event()
    calls = []
    def operation():
        calls.append(True)
        raise PermissionError('locked')
    with recovery_context(cancel=cancel, sleep=lambda seconds: cancel.set()):
        with pytest.raises(RunFailure) as failure:
            retry_operation(operation, stage='excel_replace')
    assert failure.value.code == 'CANCELLED'
    assert len(calls) == 1
    with recovery_context(cancel=cancel):
        with pytest.raises(RunFailure):
            wait_before_retry(60)


def test_cancel_does_not_prevent_critical_file_restoration():
    from threading import Event
    from molstat.recovery import uncancellable_cleanup, check_cancelled
    cancel = Event()
    cancel.set()
    calls = []
    with recovery_context(cancel=cancel):
        with uncancellable_cleanup():
            retry_operation(lambda: calls.append('restored'), stage='public_rollback')
        with pytest.raises(RunFailure):
            check_cancelled()
    assert calls == ['restored']
