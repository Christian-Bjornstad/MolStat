from datetime import datetime, timedelta, timezone
from pathlib import Path

from molstat.database import MolStatDatabase
from molstat.orchestrator import MolStatOrchestrator


def test_successful_job_is_recorded_without_sensitive_summary(
    tmp_path: Path,
) -> None:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    orchestrator = MolStatOrchestrator(
        database,
        {"statistics": lambda: {"rows": 42, "path": "K:/secret/SAMPLE-1.csv"}},
        owner="pc-a",
    )

    result = orchestrator.run("statistics", "manual")

    assert result.status == "succeeded"
    assert result.summary == {"rows": 42}
    assert database.job_statuses() == (("statistics", "succeeded"),)


def test_failed_job_does_not_block_next_job_or_leak_exception(
    tmp_path: Path,
) -> None:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()

    def fail() -> dict[str, int]:
        raise RuntimeError("SECRET-SAMPLE-42 at K:/sensitive/raw.csv")

    failed = MolStatOrchestrator(
        database, {"statistics": fail}, owner="pc-a"
    ).run("statistics", "manual")
    succeeded = MolStatOrchestrator(
        database, {"backlog": lambda: {"rows": 1}}, owner="pc-a"
    ).run("backlog", "manual")

    assert failed.status == "failed"
    assert "SECRET" not in (failed.message or "")
    assert "K:/" not in (failed.message or "")
    assert succeeded.status == "succeeded"
    assert database.job_statuses() == (
        ("statistics", "failed"),
        ("backlog", "succeeded"),
    )


def test_failed_job_reports_exception_to_private_diagnostic_boundary(
    tmp_path: Path,
) -> None:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    reported: list[tuple[str, BaseException]] = []
    failure = RuntimeError("SECRET-SAMPLE-42")

    def fail() -> dict[str, int]:
        raise failure

    orchestrator = MolStatOrchestrator(
        database,
        {"statistics": fail},
        owner="pc-a",
        failure_reporter=lambda stage, error: reported.append((stage, error)),
    )

    result = orchestrator.run("statistics", "manual")

    assert result.status == "failed"
    assert reported == [("statistics_run_failed", failure)]
    assert "SECRET" not in (result.message or "")


def test_active_writer_returns_busy_without_running_job(tmp_path: Path) -> None:
    now = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
    database = MolStatDatabase(tmp_path / "molstat.sqlite3", now=lambda: now)
    database.migrate()
    called = False

    def runner() -> dict[str, int]:
        nonlocal called
        called = True
        return {"rows": 1}

    orchestrator = MolStatOrchestrator(
        database,
        {"backlog": runner},
        owner="pc-b",
        lease_ttl=timedelta(minutes=30),
    )

    with database.writer_lease("pc-a", timedelta(minutes=30)):
        result = orchestrator.run("backlog", "scheduled")

    assert result.status == "busy"
    assert called is False
