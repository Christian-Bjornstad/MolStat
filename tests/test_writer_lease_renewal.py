from datetime import timedelta
import threading

import pytest

from molstat.database import MolStatDatabase, WriterLeaseBusy
from molstat.orchestrator import MolStatOrchestrator


def test_renewing_lease_keeps_long_running_job_owned(tmp_path):
    database = MolStatDatabase(tmp_path / "database.sqlite3")
    database.migrate()
    renewed = threading.Event()
    renewals = []

    with database.writer_lease("pc-a", timedelta(milliseconds=600), renew=True) as lease:
        original = lease.renew

        def observe_renewal():
            original()
            renewals.append(True)
            if len(renewals) >= 4:
                renewed.set()

        lease.renew = observe_renewal
        assert renewed.wait(2), "The active lease must be renewed by its heartbeat"
        assert database.current_lease_owner() == "pc-a"
        with pytest.raises(WriterLeaseBusy):
            with database.writer_lease("pc-b", timedelta(seconds=5)):
                pytest.fail("A renewed long-running job cannot be taken over")
        assert lease.thread.is_alive()

    assert not lease.thread.is_alive()
    assert database.current_lease_owner() is None


def test_stolen_token_blocks_database_mutation_from_rebuilt_database(tmp_path):
    from molstat._writer_lease import WriterLeaseLost

    path = tmp_path / "database.sqlite3"
    database = MolStatDatabase(path)
    database.migrate()
    with database.writer_lease("pc-a", timedelta(seconds=10), renew=True) as lease:
        with database._connect(guard_lease=False) as connection:
            connection.execute("UPDATE writer_lease SET token='replacement', owner='pc-b'")
        rebuilt = MolStatDatabase(path)
        with pytest.raises(WriterLeaseLost):
            with rebuilt._connect() as connection:
                connection.execute("INSERT INTO job_run(kind,trigger,status,started_at) VALUES ('test','manual','running','now')")
        with pytest.raises(WriterLeaseLost):
            lease.renew()
    assert database.current_lease_owner() == "pc-b"
    with database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM job_run").fetchone()[0] == 0


def test_stale_writer_cannot_publish_or_archive_shared_outputs(tmp_path):
    from datetime import date
    from molstat._writer_lease import WriterLeaseLost
    from molstat.archive import RawArchive
    from molstat.lvms.report import ReportRequest
    from molstat.publisher import PublicationPolicy, SharePointPublisher

    database = MolStatDatabase(tmp_path / "data/database.sqlite3")
    database.migrate()
    source = tmp_path / "source.csv"
    source.write_text("Analyse;Antall\nSYNTHETIC;1\n")
    publisher = SharePointPublisher(PublicationPolicy({"antall.csv": frozenset({"Analyse", "Antall"})}, ()))
    with database.writer_lease("pc-a", timedelta(seconds=10), renew=True):
        with database._connect(guard_lease=False) as connection:
            connection.execute("UPDATE writer_lease SET token='replacement', owner='pc-b'")
        with pytest.raises(WriterLeaseLost):
            publisher.publish({"antall.csv": source}, tmp_path / "public")
        with pytest.raises(WriterLeaseLost):
            RawArchive(tmp_path).store(source, ReportRequest("statistics", "flow", "REPORT", date.today(), date.today()))
    assert not (tmp_path / "public").exists()
    assert not (tmp_path / "data" / "raw").exists()


def test_orchestrator_renews_and_releases_lease_when_runner_fails(tmp_path):
    database = MolStatDatabase(tmp_path / "database.sqlite3")
    database.migrate()
    active_threads = []

    def fail():
        from molstat._writer_lease import active_writer_lease
        lease = active_writer_lease(database.path)
        assert lease is not None
        active_threads.append(lease.thread)
        raise RuntimeError("private failure")

    result = MolStatOrchestrator(database, {"test": fail}, owner="pc").run("test", "manual")

    assert result.status == "failed"
    assert active_threads and not active_threads[0].is_alive()
    assert database.current_lease_owner() is None


def test_long_transaction_renews_while_still_holding_the_write_lock(tmp_path):
    from datetime import datetime, timezone

    clock = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
    database = MolStatDatabase(tmp_path / "database.sqlite3", now=lambda: clock[0])
    database.migrate()
    with database.writer_lease("pc-a", timedelta(seconds=30), renew=True):
        with database._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO job_run(kind,trigger,status,started_at) VALUES ('test','manual','running','now')")
            clock[0] += timedelta(minutes=2)
            connection.execute("COMMIT")
        assert database.current_lease_owner() == "pc-a"
        with pytest.raises(WriterLeaseBusy):
            with database.writer_lease("pc-b", timedelta(seconds=30)):
                pytest.fail("An import commit must refresh the active owner's expiry")
    with database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM job_run").fetchone()[0] == 1


def test_token_changed_after_connection_open_is_fenced_at_begin(tmp_path):
    from molstat._writer_lease import WriterLeaseLost

    database = MolStatDatabase(tmp_path / "database.sqlite3")
    database.migrate()
    with database.writer_lease("pc-a", timedelta(seconds=30), renew=True):
        with database._connect() as connection:
            with database._connect(guard_lease=False) as outsider:
                outsider.execute("UPDATE writer_lease SET token='new-owner'")
            with pytest.raises(WriterLeaseLost):
                connection.execute("BEGIN IMMEDIATE")
            assert not connection.in_transaction


def test_token_changed_after_connection_open_is_fenced_for_autocommit(tmp_path):
    from molstat._writer_lease import WriterLeaseLost

    database = MolStatDatabase(tmp_path / "database.sqlite3")
    database.migrate()
    with database.writer_lease("pc-a", timedelta(seconds=30), renew=True):
        with database._connect() as connection:
            with database._connect(guard_lease=False) as outsider:
                outsider.execute("UPDATE writer_lease SET token='new-owner'")
            with pytest.raises(WriterLeaseLost):
                connection.execute("INSERT INTO job_run(kind,trigger,status,started_at) VALUES ('test','manual','running','now')")
            assert not connection.in_transaction
    with database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM job_run").fetchone()[0] == 0


def test_lost_lease_does_not_report_success_or_write_failed_status_using_successor_token(tmp_path):
    database = MolStatDatabase(tmp_path / "database.sqlite3")
    database.migrate()

    def runner():
        with database._connect(guard_lease=False) as connection:
            connection.execute("UPDATE writer_lease SET token='replacement', owner='pc-b'")
        return {"rows": 2}

    result = MolStatOrchestrator(database, {"test": runner}, owner="pc-a").run("test", "manual")

    assert result.status == "failed"
    assert "Databaselåsen" in result.message
    assert database.current_lease_owner() == "pc-b"
    with database._connect() as connection:
        assert connection.execute("SELECT status FROM job_run").fetchone()[0] == "running"


@pytest.mark.parametrize("commit_style", ["method", "context"])
def test_transaction_commit_styles_renew_before_releasing_lock(tmp_path, commit_style):
    from datetime import datetime, timezone

    clock = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
    database = MolStatDatabase(tmp_path / "database.sqlite3", now=lambda: clock[0])
    database.migrate()
    with database.writer_lease("pc-a", timedelta(seconds=30), renew=True):
        with database._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO job_run(kind,trigger,status,started_at) VALUES ('test','manual','running','now')")
            clock[0] += timedelta(minutes=2)
            if commit_style == "method":
                connection.commit()
        assert database.current_lease_owner() == "pc-a"


def test_single_transient_heartbeat_io_error_does_not_poison_the_run(tmp_path):
    import sqlite3

    database = MolStatDatabase(tmp_path / 'database.sqlite3')
    database.migrate()
    recovered = threading.Event()
    calls = []
    with database.writer_lease('pc-a', timedelta(milliseconds=900), renew=True) as lease:
        original = lease.renew
        def intermittent_renew():
            calls.append(1)
            if len(calls) == 1:
                error = sqlite3.OperationalError('synthetic temporary I/O failure')
                error.sqlite_errorcode = sqlite3.SQLITE_IOERR
                error.sqlite_errorname = 'SQLITE_IOERR'
                raise error
            original()
            recovered.set()
        lease.renew = intermittent_renew
        assert recovered.wait(2), 'Heartbeat must recover after a transient I/O error'
        assert not lease.lost.is_set()
        with database._connect() as connection:
            connection.execute("INSERT INTO job_run(kind,trigger,status,started_at) VALUES ('test','manual','running','now')")


@pytest.mark.parametrize('operation', ['renew', 'output'])
def test_delayed_owner_can_renew_only_if_token_is_still_unchanged(tmp_path, operation):
    from datetime import datetime, timezone

    clock = [datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)]
    database = MolStatDatabase(tmp_path / 'database.sqlite3', now=lambda: clock[0])
    database.migrate()
    with database.writer_lease('pc-a', timedelta(seconds=30), renew=True) as lease:
        clock[0] += timedelta(minutes=2)
        if operation == 'renew':
            lease.renew()
        else:
            with lease.output_guard():
                pass
        assert database.current_lease_owner() == 'pc-a'


def test_persistent_heartbeat_io_failure_still_stops_before_further_writes(tmp_path):
    import sqlite3
    from molstat._writer_lease import WriterLeaseLost

    database = MolStatDatabase(tmp_path / 'database.sqlite3')
    database.migrate()
    with database.writer_lease('pc-a', timedelta(milliseconds=300), renew=True) as lease:
        original = lease.renew
        def unavailable():
            error = sqlite3.OperationalError('synthetic storage unavailable')
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            error.sqlite_errorname = 'SQLITE_IOERR'
            raise error
        lease.renew = unavailable
        assert lease.lost.wait(2)
        assert lease.loss_reason == 'SQLITE_IOERR'
        lease.renew = original
        with pytest.raises(WriterLeaseLost):
            with lease.output_guard():
                pytest.fail('No files may be installed after confirmed lease loss')


def test_delayed_owner_cannot_reclaim_a_token_taken_by_a_real_successor(tmp_path):
    from datetime import datetime, timezone
    from molstat._writer_lease import WriterLeaseLost

    clock = [datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)]
    database = MolStatDatabase(tmp_path / 'database.sqlite3', now=lambda: clock[0])
    database.migrate()
    with database.writer_lease('pc-a', timedelta(seconds=30), renew=True) as old:
        clock[0] += timedelta(minutes=2)
        with database.writer_lease('pc-b', timedelta(minutes=5)):
            with pytest.raises(WriterLeaseLost):
                old.renew()
            with database.read_connection() as connection:
                assert connection.execute('SELECT owner FROM writer_lease').fetchone()[0] == 'pc-b'


def test_lost_writer_does_not_start_another_pathology_download(tmp_path):
    from datetime import date
    from molstat._writer_lease import WriterLeaseLost
    from molstat.fetching import UnifiedLvmsFetcher, _statistics_job
    from molstat.unit_settings import load_unit_file
    from unit_fixtures import default_unit_file

    database = MolStatDatabase(tmp_path / 'database.sqlite3')
    database.migrate()
    calls = []
    unit = load_unit_file(default_unit_file('lege')).unit
    job = _statistics_job(unit, unit.report_by_key('workflow'), date(2026, 9, 1), date(2026, 9, 30))
    fetcher = UnifiedLvmsFetcher(lvms_config_path=tmp_path / 'lvms.json',
        sensitive_root=tmp_path, work_root=tmp_path / 'fetch', units_path=tmp_path / 'units.json',
        backlog_report_path=tmp_path / 'backlog.json', run_batch=lambda *a, **kw: calls.append(1) or 0)
    with database.writer_lease('pc-a', timedelta(minutes=5), renew=True):
        with database._connect(guard_lease=False) as connection:
            connection.execute("UPDATE writer_lease SET token='other', owner='pc-b'")
        with pytest.raises(WriterLeaseLost):
            fetcher._run_jobs((job,), 'lege')
    assert calls == []
    assert not (tmp_path / 'fetch').exists()


def test_file_error_after_delayed_resume_does_not_rollback_the_lease_renewal(tmp_path):
    from datetime import datetime, timezone

    clock = [datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)]
    database = MolStatDatabase(tmp_path / 'database.sqlite3', now=lambda: clock[0])
    database.migrate()
    with database.writer_lease('pc-a', timedelta(seconds=30), renew=True) as lease:
        clock[0] += timedelta(minutes=2)
        with pytest.raises(PermissionError):
            with lease.output_guard():
                raise PermissionError('synthetic locked Power BI file')
        assert database.current_lease_owner() == 'pc-a'
        assert not lease.lost.is_set()
