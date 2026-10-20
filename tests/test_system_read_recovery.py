import pytest

def test_excel_snapshot_busy_read_is_retried_without_repeating_import(tmp_path, monkeypatch):
    from datetime import datetime
    import sqlite3
    from molstat.database import MolStatDatabase
    from molstat.system import MolStatSystem
    from molstat.excel_search import read_excel_snapshot
    database = MolStatDatabase(tmp_path / 'private/database/molstat.sqlite3')
    database.migrate()
    system = object.__new__(MolStatSystem)
    system.database = database
    system.excel_search_path = tmp_path / 'Prøvesøk.xlsx'
    system._excel_now = lambda: datetime(2026, 10, 20, 12)
    system._excel_failure_reporter = None
    denied = []
    def locked_once(db, **kwargs):
        if not denied:
            denied.append(True)
            error = sqlite3.OperationalError('SECRET-PATH')
            error.sqlite_errorcode = sqlite3.SQLITE_BUSY
            error.sqlite_errorname = 'SQLITE_BUSY'
            raise error
        return read_excel_snapshot(db, **kwargs)
    monkeypatch.setattr('molstat.system.read_excel_snapshot', locked_once)

    assert system._refresh_excel_search() is True

    assert system.excel_search_path.is_file()
    assert system.excel_status.status == 'published'

def test_cancel_after_archive_prevents_business_import(tmp_path, monkeypatch):
    from threading import Event
    from types import SimpleNamespace
    from datetime import date
    import pytest
    from molstat.archive import RawArchive
    from molstat.failures import RunFailure
    from molstat.lvms.report import ReportRequest
    from molstat.modules import DEFAULT_UNITS
    from molstat.recovery import recovery_context
    from molstat.system import MolStatSystem
    source = tmp_path / 'source.csv'
    source.write_bytes(b'SYNTHETIC')
    cancelled = Event()
    system = object.__new__(MolStatSystem)
    system.units = DEFAULT_UNITS
    system.capability_errors = {}
    imported = []
    system.statistics_processors = {'flow': SimpleNamespace(process=lambda *a: imported.append(True))}
    system.archive = RawArchive(tmp_path / 'private')
    system.work_root = tmp_path / 'processed'
    system._excel_failure_reporter = None
    original = system.archive.store
    def archive_then_cancel(source, request):
        result = original(source, request)
        cancelled.set()
        return result
    monkeypatch.setattr(system.archive, 'store', archive_then_cancel)
    report = ReportRequest(kind='statistics', unit='flow', report_name='SYNTHETIC',
                           date_from=date(2026, 10, 1), date_to=date(2026, 10, 2))

    with recovery_context(cancel=cancelled):
        with pytest.raises(RunFailure) as caught:
            system._process_statistics('flow', ((report, source),))

    assert caught.value.code == 'CANCELLED'
    assert imported == []
    assert list((tmp_path / 'private/data/raw/statistics/flow').glob('*.csv'))

@pytest.mark.parametrize('failure_kind', ['cancel', 'lease_lost'])
def test_excel_refresh_does_not_swallow_terminal_job_failure(tmp_path, monkeypatch, failure_kind):
    from datetime import datetime
    import pytest
    from molstat.failures import RunFailure
    from molstat._writer_lease import WriterLeaseLost
    from molstat.system import MolStatSystem
    system = object.__new__(MolStatSystem)
    system.database = None
    system.excel_search_path = tmp_path / 'Prøvesøk.xlsx'
    system._excel_now = datetime.now
    system._excel_failure_reporter = None
    error = RunFailure('CANCELLED', 'cancelled') if failure_kind == 'cancel' else WriterLeaseLost('SYNTHETIC')
    monkeypatch.setattr('molstat.system.read_excel_snapshot', lambda *a, **kw: (_ for _ in ()).throw(error))

    with pytest.raises(type(error)):
        system._refresh_excel_search()


def test_run_all_stops_before_next_capability_after_cancel(tmp_path, monkeypatch):
    from molstat.failures import RunFailure
    from molstat.modules import DEFAULT_UNITS
    from molstat.system import MolStatSystem
    import pytest
    system = object.__new__(MolStatSystem)
    system.units = DEFAULT_UNITS
    calls = []
    def cancel_first(unit, kind):
        calls.append((unit, kind))
        raise RunFailure('CANCELLED', 'cancelled')
    monkeypatch.setattr(system, '_run_capability', cancel_first)

    with pytest.raises(RunFailure):
        system.run_all(('hemato', 'flow'))

    assert calls == [('hemato', 'statistics')]
