import sqlite3

from molstat.failures import RunFailure, database_failure


def test_failure_does_not_expose_exception_payload():
    error = sqlite3.OperationalError("SECRET-PATIENT")
    error.sqlite_errorname = "SQLITE_BUSY"
    failure = database_failure(error)
    assert failure.code == "DB_BUSY"
    assert "SECRET" not in str(failure)
    assert "SQLITE_BUSY" in str(failure)


def test_failure_contains_actionable_stage_and_attempt():
    failure = RunFailure("LVMS_TIMEOUT", "lvms_open", attempt=2, run_id="abc")
    assert "lvms_open" in str(failure)
    assert "2" in str(failure)
    assert "abc" in str(failure)


def test_database_failure_keeps_controlled_stage_and_numeric_os_error():
    error = sqlite3.OperationalError('SECRET-PATIENT-PATH')
    error.sqlite_errorname = 'SQLITE_READONLY_DIRECTORY'
    error.sqlite_errorcode = sqlite3.SQLITE_READONLY_DIRECTORY
    error.database_stage = 'database_directory'
    error.os_errorcode = 5
    failure = database_failure(error)
    assert failure.code == 'DB_ACCESS'
    assert failure.stage == 'database_directory'
    assert 'OS_ERROR=5' in failure.detail
    assert 'SQLITE_READONLY_DIRECTORY' in failure.detail
    assert 'SECRET' not in str(failure)


def test_external_error_fields_cannot_inject_private_text():
    error = sqlite3.OperationalError('SECRET-PATIENT')
    error.sqlite_errorname = 'SQLITE_READONLY SECRET-PATIENT'
    error.sqlite_errorcode = sqlite3.SQLITE_READONLY
    error.database_stage = 'SECRET-PATIENT'
    error.os_errorcode = 'SECRET-PATIENT'
    failure = database_failure(error)
    assert failure.code == 'DB_ACCESS'
    assert 'SECRET' not in str(failure)
