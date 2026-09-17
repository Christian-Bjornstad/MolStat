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
