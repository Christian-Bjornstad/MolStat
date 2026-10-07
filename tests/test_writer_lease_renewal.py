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
    assert not (tmp_path / "raw").exists()


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
