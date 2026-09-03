import json
from datetime import datetime, timedelta

from molstat.backlog import AnalysisConfig, AppConfig, ThresholdsConfig, UnitConfig
from molstat.backlog import Severity, build_dashboard_snapshot
from molstat.backlog import Sample, WorkflowStage


def config() -> AppConfig:
    return AppConfig(
        report_id="PAT-DIT-RESTANSE-OU",
        unit=UnitConfig("hemato", "MolPat hemato"),
        thresholds=ThresholdsConfig(warning_hours=6, critical_hours=12),
        analyses=(
            AnalysisConfig(
                code="A",
                label="Analyse A",
                group="Gruppe",
                priority="standard",
                warning_hours=6,
                critical_hours=12,
            ),
            AnalysisConfig(
                code="EMPTY",
                label="Tom analyse",
                group="Gruppe",
                priority="standard",
                warning_hours=6,
                critical_hours=12,
            ),
        ),
    )


def sample(
    sample_id: str,
    stage: WorkflowStage,
    *,
    arrived: datetime | None,
    ordered: datetime | None = None,
) -> Sample:
    return Sample(
        sample_id,
        "A",
        ordered or datetime(2026, 1, 1, 8, 0),
        arrived,
        stage,
    )


def test_ready_age_uses_arrival_and_reports_median_oldest_overdue():
    now = datetime(2026, 8, 31, 12, 0)
    samples = [
        sample("S1", WorkflowStage.READY, arrived=now - timedelta(hours=2)),
        sample("S2", WorkflowStage.READY, arrived=now - timedelta(hours=6)),
        sample("S3", WorkflowStage.READY, arrived=now - timedelta(hours=24)),
    ]

    summary = build_dashboard_snapshot(
        config(), samples, now, timedelta(minutes=2)
    ).analyses[0]

    assert summary.median_ready_hours == 6.0
    assert summary.oldest_ready_hours == 24.0
    assert summary.overdue == 1
    assert summary.severity is Severity.OVERDUE


def test_ready_age_falls_back_to_ordered_time_when_arrival_is_missing():
    now = datetime(2026, 8, 31, 12, 0)
    samples = [
        sample(
            "S1",
            WorkflowStage.READY,
            arrived=None,
            ordered=now - timedelta(hours=4),
        ),
        sample(
            "S2",
            WorkflowStage.READY,
            arrived=None,
            ordered=now - timedelta(hours=10),
        ),
    ]

    summary = build_dashboard_snapshot(
        config(), samples, now, timedelta(minutes=2)
    ).analyses[0]

    assert summary.median_ready_hours == 7.0
    assert summary.oldest_ready_hours == 10.0


def test_warning_boundary_and_non_ready_stages_do_not_affect_age():
    now = datetime(2026, 8, 31, 12, 0)
    samples = [
        sample("S1", WorkflowStage.READY, arrived=now - timedelta(hours=6)),
        sample(
            "S2",
            WorkflowStage.AWAITING_APPROVAL,
            arrived=None,
            ordered=now - timedelta(days=100),
        ),
        sample(
            "S3",
            WorkflowStage.IN_TRANSIT,
            arrived=None,
            ordered=now - timedelta(days=200),
        ),
    ]

    summary = build_dashboard_snapshot(
        config(), samples, now, timedelta(minutes=2)
    ).analyses[0]

    assert summary.median_ready_hours == 6.0
    assert summary.oldest_ready_hours == 6.0
    assert summary.severity is Severity.WARNING
    assert summary.awaiting_approval == 1
    assert summary.in_transit == 1


def test_public_payload_has_totals_but_no_sample_identifiers():
    now = datetime(2026, 8, 31, 12, 0)
    samples = [
        sample("S-SECRET-READY", WorkflowStage.READY, arrived=now - timedelta(hours=2)),
        sample("S-SECRET-APPROVAL", WorkflowStage.AWAITING_APPROVAL, arrived=None),
        sample("S-SECRET-TRANSIT", WorkflowStage.IN_TRANSIT, arrived=None),
    ]

    snapshot = build_dashboard_snapshot(config(), samples, now, timedelta(minutes=2))
    payload = snapshot.to_public_dict()
    encoded = json.dumps(payload)

    assert payload["totals"] == {
        "ready": 1,
        "awaitingApproval": 1,
        "inTransit": 1,
        "overdue": 0,
    }
    assert payload["emptyAnalysisCount"] == 1
    assert "S-SECRET" not in encoded
    assert "sample" not in encoded.casefold()


def test_future_arrival_is_clamped_and_stale_state_is_reported():
    now = datetime(2026, 8, 31, 12, 0)
    snapshot = build_dashboard_snapshot(
        config(),
        [sample("S1", WorkflowStage.READY, arrived=now + timedelta(hours=1))],
        now,
        timedelta(minutes=2),
        source_updated_at=now - timedelta(minutes=3),
    )

    assert snapshot.analyses[0].oldest_ready_hours == 0.0
    assert snapshot.is_stale

