"""Windows protection and SQLite automatic-abort regressions; synthetic only."""
from datetime import datetime, timedelta
import os
import sqlite3
import stat

import pytest

from molstat.database import MolStatDatabase
from molstat.orchestrator import MolStatOrchestrator


def database(tmp_path):
    value = MolStatDatabase(tmp_path / 'molstat.sqlite3')
    value.migrate()
    return value


def abort_trigger(db, table, operation='INSERT'):
    with db._connect(guard_lease=False) as connection:
        connection.execute(f"CREATE TRIGGER synthetic_abort BEFORE {operation} ON {table} BEGIN SELECT RAISE(ROLLBACK, 'SYNTHETIC_ABORT'); END")


def assert_original_abort(error):
    assert error.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_TRIGGER


def import_hemato(db, tmp_path):
    from backlog.test_processor import _config, _contract
    from molstat.backlog import BacklogProcessor
    source = tmp_path / 'synthetic.csv'
    source.write_text('SampleID;Analyse;Tidspunkt analysebestilling;Tidspunkt ankomst;Status analyse;Analyseresultat\nSYNTHETIC;IGH-OU;30.08.2026 07:00;30.08.2026 08:00;Initial;\n', encoding='cp1252')
    processor = BacklogProcessor(_config(), _contract(), now=lambda: datetime(2026, 9, 2, 8))
    processor.import_snapshot(source, db)


def test_acquisition_preserves_original_error_after_sqlite_automatic_rollback(tmp_path):
    db = database(tmp_path)
    abort_trigger(db, 'writer_lease')
    with pytest.raises(sqlite3.IntegrityError) as error:
        with db.writer_lease('synthetic', timedelta(minutes=5)):
            pytest.fail('A rejected acquisition cannot start the runner')
    assert_original_abort(error)


def test_guarded_autocommit_preserves_original_error_after_automatic_rollback(tmp_path):
    db = database(tmp_path)
    abort_trigger(db, 'job_run')
    with db.writer_lease('synthetic', timedelta(minutes=5), renew=True):
        with pytest.raises(sqlite3.IntegrityError) as error:
            with db._connect() as connection:
                connection.execute("INSERT INTO job_run(kind, trigger, status, started_at) VALUES ('synthetic','manual','running','now')")
        assert_original_abort(error)


def test_renewal_preserves_original_error_after_automatic_rollback(tmp_path):
    db = database(tmp_path)
    with db.writer_lease('synthetic', timedelta(minutes=5), renew=True) as lease:
        abort_trigger(db, 'writer_lease', 'UPDATE')
        with pytest.raises(sqlite3.IntegrityError) as error:
            lease.renew()
        assert_original_abort(error)


def test_hemato_import_preserves_original_error_and_previous_snapshot(tmp_path):
    from backlog.test_processor import _config, _contract
    from molstat.backlog import BacklogProcessor
    db = database(tmp_path)
    source = tmp_path / 'synthetic.csv'
    source.write_text('SampleID;Analyse;Tidspunkt analysebestilling;Tidspunkt ankomst;Status analyse;Analyseresultat\nSYNTHETIC;IGH-OU;30.08.2026 07:00;30.08.2026 08:00;Initial;\n', encoding='cp1252')
    processor = BacklogProcessor(_config(), _contract(), now=lambda: datetime(2026, 9, 2, 8))
    processor.import_snapshot(source, db)
    before = processor.public_snapshot(db, datetime(2026, 9, 2, 9))
    abort_trigger(db, 'import_run')
    with pytest.raises(sqlite3.IntegrityError) as error:
        processor.import_snapshot(source, db)
    assert_original_abort(error)
    assert processor.public_snapshot(db, datetime(2026, 9, 2, 9)) == before


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows read-only attributes')
@pytest.mark.parametrize('protected', ['database', 'journal'])
def test_writer_recovers_known_windows_readonly_attributes(tmp_path, protected):
    db = database(tmp_path)
    target = db.path if protected == 'database' else db.path.with_name(db.path.name + '-journal')
    if protected == 'journal':
        target.touch()
    target.chmod(stat.S_IREAD)
    try:
        with db.writer_lease('synthetic', timedelta(minutes=5)):
            import_hemato(db, tmp_path)
            with db._connect() as connection:
                assert connection.execute('SELECT version FROM schema_info').fetchone() == (7,)
                assert connection.execute('SELECT COUNT(*) FROM backlog_current').fetchone() == (1,)
        assert db.schema_version() == 7
    finally:
        if target.exists():
            target.chmod(stat.S_IWRITE)


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows read-only attributes')
def test_readonly_flag_changed_during_long_fetch_is_repaired_on_new_connection(tmp_path):
    db = database(tmp_path)
    def fetch_then_import():
        db.path.chmod(stat.S_IREAD)
        import_hemato(db, tmp_path)
        return {'rows': 1}
    runner = MolStatOrchestrator(db, {'hemato': fetch_then_import}, owner='synthetic')
    try:
        result = runner.run('hemato', 'manual')
        assert result.status == 'succeeded'
    finally:
        if db.path.exists():
            db.path.chmod(stat.S_IWRITE)
    with db.read_connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM job_run').fetchone() == (1,)
        assert connection.execute('SELECT COUNT(*) FROM backlog_current').fetchone() == (1,)
        assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows read-only attributes')
def test_read_apis_and_backups_do_not_repair_file_attributes(tmp_path):
    from molstat.backup import create_verified_backup
    from molstat.registry import SampleRegistry
    db = database(tmp_path)
    db.path.chmod(stat.S_IREAD)
    try:
        assert db.schema_version() == 7
        assert db.table_names()
        assert db.current_lease_owner() is None
        assert db.job_statuses() == ()
        assert db.last_successes() == {'statistics': None, 'backlog': None}
        assert SampleRegistry(db).counts() == (0, 0)
        assert SampleRegistry(db).search('SYNTHETIC') == ()
        assert SampleRegistry(db).molstat_ids() == {}
        assert MolStatOrchestrator(db, {}, owner='synthetic').capability_statuses() == ()
        assert create_verified_backup(db, tmp_path / 'backups').path.is_file()
        assert db.path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
    finally:
        db.path.chmod(stat.S_IWRITE)


def test_storage_denial_is_reported_before_fetch_and_never_replayed(tmp_path, monkeypatch):
    db = database(tmp_path)
    called = []
    errors = []
    def deny(path):
        error = sqlite3.OperationalError('SECRET-PATH-PATIENT')
        error.sqlite_errorcode = sqlite3.SQLITE_READONLY_DIRECTORY
        error.sqlite_errorname = 'SQLITE_READONLY_DIRECTORY'
        error.database_stage = 'database_directory'
        raise error
    monkeypatch.setattr('molstat.database.probe_writer_directory', deny, raising=False)
    runner = MolStatOrchestrator(db, {'hemato': lambda: called.append(True) or {}}, owner='synthetic',
        failure_reporter=lambda name, error: errors.append(error))
    result = runner.run('hemato', 'manual')
    assert result.status == 'failed'
    assert called == []
    assert len(errors) == 1
    assert 'DB_ACCESS' in result.message
    assert 'database_directory' in result.message
    assert 'SECRET' not in result.message
