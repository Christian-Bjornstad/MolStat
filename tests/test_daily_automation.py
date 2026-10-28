from datetime import datetime, timedelta, timezone

import pytest

from molstat.database import MolStatDatabase
from molstat.orchestrator import MolStatOrchestrator


LOCAL = timezone(timedelta(hours=1))
MORNING = datetime(2026, 10, 28, 7, tzinfo=LOCAL)


def test_daily_run_catches_up_and_survives_restart_and_second_pc(tmp_path):
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    calls = []
    clock = [MORNING]

    def orchestrator(owner):
        return MolStatOrchestrator(database, {"all": lambda: calls.append(owner) or {}},
                                  owner=owner, now=lambda: clock[0])

    first = orchestrator("pc-a")
    assert first.run_daily(now=MORNING - timedelta(seconds=1)) is None
    assert first.run_daily(now=MORNING).status == "succeeded"
    assert orchestrator("pc-b").run_daily(now=MORNING.replace(hour=12)) is None
    clock[0] += timedelta(days=1, hours=3)
    assert orchestrator("pc-b").run_daily(now=clock[0]).status == "succeeded"
    assert calls == ["pc-a", "pc-b"]
    assert database.job_statuses() == (("all", "succeeded"), ("all", "succeeded"))


@pytest.mark.parametrize("fail", (False, True))
def test_manual_runs_do_not_consume_daily_schedule_and_failure_does_not_loop(tmp_path, fail):
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()

    def runner():
        if fail:
            raise RuntimeError("synthetic")
        return {}

    orchestrator = MolStatOrchestrator(database, {"all": runner}, owner="pc-a", now=lambda: MORNING)
    orchestrator.run("all", "manual")
    result = orchestrator.run_daily(now=MORNING)
    assert result.status == ("failed" if fail else "succeeded")
    assert orchestrator.run_daily(now=MORNING + timedelta(minutes=1)) is None
    assert len(database.job_statuses()) == 2


def test_busy_daily_run_waits_without_consuming_today(tmp_path):
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    orchestrator = MolStatOrchestrator(database, {"all": lambda: {}}, owner="pc-b", now=lambda: MORNING)
    with database.writer_lease("pc-a", timedelta(minutes=30)):
        assert orchestrator.run_daily(now=MORNING).status == "busy"
        assert database.job_statuses() == ()
    assert orchestrator.run_daily(now=MORNING).status == "succeeded"


def test_abandoned_attempt_can_resume_after_lease_has_gone(tmp_path):
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    with database._connect() as connection:
        connection.execute("INSERT INTO job_run(kind, trigger, status, started_at) VALUES ('all', 'scheduled:2026-10-28T07:00', 'running', ?)",
                           (MORNING.astimezone(timezone.utc).isoformat(),))
    orchestrator = MolStatOrchestrator(database, {"all": lambda: {}}, owner="pc-a", now=lambda: MORNING)
    assert orchestrator.run_daily(now=MORNING).status == "succeeded"


def test_daily_service_uses_all_capabilities_of_only_saved_enabled_units(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from dataclasses import replace
    from molstat.modules import DEFAULT_UNITS
    from molstat.services import DefaultServices
    from molstat.system import CapabilityRun

    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    services = DefaultServices(tmp_path / "settings.json")
    services.settings = replace(services.settings, enabled_units=("hemato", "flow", "lege"), daily_time="08:35")
    called = []

    def run_all(enabled):
        called.append(enabled)
        return tuple(CapabilityRun(unit.key, capability.job_kind, {"published": 1})
                     for unit in DEFAULT_UNITS.active(enabled) for capability in unit.capabilities)

    system = SimpleNamespace(database=database, units=DEFAULT_UNITS, run_all=run_all)
    monkeypatch.setattr(services, "_build_system", lambda **kwargs: system)
    orchestrator = services._orchestrator(system)
    start = MORNING.replace(hour=8, minute=35)
    orchestrator._now = lambda: start
    assert orchestrator.run_daily(now=start - timedelta(seconds=1)) is None
    result = orchestrator.run_daily(now=start)
    assert called == [("hemato", "flow", "lege")]
    assert {(item.unit_key, item.job_kind) for item in result.capability_results} == {
        ("hemato", "statistics"), ("hemato", "backlog"), ("flow", "statistics"), ("lege", "statistics")}
    assert result.status == "succeeded"
    with database.read_connection() as connection:
        assert connection.execute("SELECT kind, trigger FROM job_run").fetchall() == [("all", "scheduled:2026-10-28T08:35")]


def test_cancelled_daily_run_stays_stopped_until_next_day(tmp_path):
    from molstat.failures import RunFailure

    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()

    def stop():
        raise RunFailure("CANCELLED", "job_run")

    orchestrator = MolStatOrchestrator(database, {"all": stop}, owner="pc-a", now=lambda: MORNING)
    assert orchestrator.run_daily(now=MORNING).error_code == "CANCELLED"
    assert orchestrator.run_daily(now=MORNING + timedelta(minutes=1)) is None


def test_new_time_runs_again_today_and_survives_restart_without_poll_loop(tmp_path):
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    original = MolStatOrchestrator(database, {"all": lambda: {}}, owner="pc-a", now=lambda: MORNING)
    assert original.run_daily(now=MORNING).status == "succeeded"
    later = MORNING.replace(hour=9, minute=15)
    updated = MolStatOrchestrator(database, {"all": lambda: {}}, owner="pc-a",
                                  now=lambda: later, daily_time="09:15")
    assert updated.run_daily(now=later - timedelta(seconds=1)) is None
    assert updated.run_daily(now=later).status == "succeeded"
    reopened = MolStatOrchestrator(database, {"all": lambda: {}}, owner="pc-b",
                                   now=lambda: later, daily_time="09:15")
    assert reopened.run_daily(now=later + timedelta(seconds=30)) is None
    assert len(database.job_statuses()) == 2


def test_legacy_daily_history_does_not_block_selected_time(tmp_path):
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    orchestrator = MolStatOrchestrator(database, {"all": lambda: {}}, owner="pc-a", now=lambda: MORNING)
    assert orchestrator.run("all", "scheduled").status == "succeeded"
    assert orchestrator.run_daily(now=MORNING).status == "succeeded"
    assert orchestrator.run_daily(now=MORNING + timedelta(seconds=30)) is None


@pytest.mark.parametrize("cancelled", (False, True))
def test_new_time_runs_after_an_earlier_failure_or_stop(tmp_path, cancelled):
    from molstat.failures import RunFailure

    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()

    def fail():
        raise RunFailure("CANCELLED", "job_run") if cancelled else RuntimeError("synthetic")

    first = MolStatOrchestrator(database, {"all": fail}, owner="pc-a", now=lambda: MORNING)
    assert first.run_daily(now=MORNING).status == "failed"
    later = MORNING.replace(hour=9, minute=15)
    updated = MolStatOrchestrator(database, {"all": lambda: {}}, owner="pc-a",
                                  now=lambda: later, daily_time="09:15")
    assert updated.run_daily(now=later).status == "succeeded"
    assert updated.run_daily(now=later + timedelta(seconds=30)) is None


def test_early_run_is_still_today_after_pc_changes_to_winter_time(tmp_path):
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    # Ask the PC for each instant's actual offset; astimezone() returns fixed
    # offsets, which can differ within the same day when the clock changes.
    early = datetime(2026, 10, 25, 0, 15).astimezone()
    later = datetime(2026, 10, 25, 8, 35).astimezone()
    first = MolStatOrchestrator(database, {"all": lambda: {}}, owner="pc-a",
                               now=lambda: early, daily_time="00:15")
    assert first.run_daily(now=early).status == "succeeded"
    reopened = MolStatOrchestrator(database, {"all": lambda: {}}, owner="pc-a",
                                  now=lambda: later, daily_time="00:15")
    assert reopened.run_daily(now=later) is None
