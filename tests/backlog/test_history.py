from datetime import datetime, timedelta, timezone

from molstat._backlog.domain import BacklogDetail
from molstat._backlog.history import (
    build_detail_history_rows,
    build_history_rows,
    hour_slot,
)
from molstat.backlog import (
    AnalysisConfig,
    AppConfig,
    Sample,
    Severity,
    ThresholdsConfig,
    UnitConfig,
    WorkflowStage,
)


def _config() -> AppConfig:
    return AppConfig(
        report_id="PAT-DIT-RESTANSE-OU",
        unit=UnitConfig("hemato", "MolPat hemato"),
        thresholds=ThresholdsConfig(warning_hours=6, critical_hours=12),
        analyses=(
            AnalysisConfig("A", "Analyse A", "Gruppe", "standard"),
            AnalysisConfig("EMPTY", "Tom analyse", "Gruppe", "standard"),
            AnalysisConfig(
                "DISABLED", "Avslått", "Gruppe", "standard", enabled=False
            ),
        ),
    )


def test_hour_slot_removes_minutes_and_preserves_timezone() -> None:
    observed = datetime(2026, 9, 7, 11, 42, 19, tzinfo=timezone(timedelta(hours=2)))

    assert hour_slot(observed) == datetime(
        2026, 9, 7, 11, 0, tzinfo=timezone(timedelta(hours=2))
    )


def test_history_contains_every_enabled_group_with_shared_dashboard_rules() -> None:
    observed = datetime(2026, 9, 7, 11, 42, 19)
    samples = (
        Sample("R1", "A", observed - timedelta(hours=20), observed - timedelta(hours=6), WorkflowStage.READY),
        Sample("R2", "A", observed - timedelta(hours=20), observed - timedelta(hours=14), WorkflowStage.READY),
        Sample("R3", "A", observed - timedelta(hours=4), None, WorkflowStage.AWAITING_APPROVAL),
        Sample("R4", "A", observed - timedelta(hours=2), None, WorkflowStage.IN_TRANSIT),
    )

    rows = build_history_rows(
        _config(),
        samples,
        observed,
        invalid_rows=2,
        excluded_rows=3,
        classifier_version=2,
    )

    assert len(rows) == 2
    assert {row.analysis_code for row in rows} == {"A", "EMPTY"}
    active = next(row for row in rows if row.analysis_code == "A")
    assert active.observed_at == datetime(2026, 9, 7, 11, 0)
    assert active.unit_key == "hemato"
    assert active.ready_count == 2
    assert active.awaiting_approval_count == 1
    assert active.in_transit_count == 1
    assert active.overdue_count == 1
    assert active.median_ready_hours == 10.0
    assert active.oldest_ready_hours == 14.0
    assert active.severity is Severity.OVERDUE
    assert active.invalid_rows == 2
    assert active.excluded_rows == 3
    assert active.source_is_fresh
    assert active.classifier_version == 2

    empty = next(row for row in rows if row.analysis_code == "EMPTY")
    assert empty.ready_count == 0
    assert empty.awaiting_approval_count == 0
    assert empty.in_transit_count == 0
    assert empty.overdue_count == 0
    assert empty.median_ready_hours is None
    assert empty.oldest_ready_hours is None
    assert empty.severity is Severity.EMPTY


def test_detail_history_keeps_approved_text_and_drops_report_group() -> None:
    observed = datetime(2026, 9, 7, 11, 42)
    detail = BacklogDetail(
        sample_id="SECRET-1",
        analysis_code="A",
        analysis_group="A",
        material="Blod",
        collected_at=datetime(2026, 9, 7, 8, 0),
        arrived_at=datetime(2026, 9, 7, 9, 0),
        ordered_at=datetime(2026, 9, 7, 9, 15),
        analysis_priority="Høy",
        request_priority="Vanlig",
        analysis_status="Initial",
        preliminary_status="Initial",
        stage=WorkflowStage.READY,
        analysis_result="Påvist – æøå",
        external_analysis_comment="Ordrett kommentar",
    )

    row = build_detail_history_rows(
        _config(),
        (detail,),
        observed,
        analysis_lookup={
            "A": {
                "Nukleinsyre": "DNA",
                "Rapportgruppe": "skal-ikke-med",
                "Svarfrist": "14",
            }
        },
        classifier_version=2,
    )[0]

    assert row.analysis_result == "Påvist – æøå"
    assert row.external_analysis_comment == "Ordrett kommentar"
    assert not hasattr(row, "report_group")
    assert "SECRET-1" not in repr(row)
