"""Tester for domenemodellen til klassifiserte restanseprøver."""

from datetime import datetime

import pytest

import molstat._backlog.domain as domain
from molstat.backlog import Sample, WorkflowStage, parse_lvms_datetime


def test_domain_exposes_only_workflow_model():
    for legacy_name in (
        "SampleStatus",
        "AgeInfo",
        "AnalysisSummary",
        "PulseSnapshot",
        "build_analysis_summary",
        "compute_age_hours",
        "normalize_status",
    ):
        assert not hasattr(domain, legacy_name), f"uventet legacy-API: {legacy_name}"


def test_sample_rejects_legacy_constructor_keywords():
    with pytest.raises(TypeError):
        Sample(
            "S1",
            "TRG-OU",
            created_at=datetime(2026, 8, 1, 8, 0),
            status="pending",
        )


def test_ready_sample_uses_arrival_as_age_anchor():
    ordered = datetime(2026, 8, 1, 8, 0)
    arrived = datetime(2026, 8, 30, 9, 0)
    sample = Sample("S1", "TRG-OU", ordered, arrived, WorkflowStage.READY)

    assert sample.age_anchor == arrived


@pytest.mark.parametrize(
    "stage",
    [WorkflowStage.AWAITING_APPROVAL, WorkflowStage.IN_TRANSIT],
)
def test_non_ready_sample_has_no_age_anchor(stage):
    sample = Sample("S1", "TRG-OU", datetime(2026, 8, 1), None, stage)

    assert sample.age_anchor is None


def test_parse_lvms_datetime_with_time():
    assert parse_lvms_datetime("15.08.2026 14:30") == datetime(2026, 8, 15, 14, 30)


def test_parse_lvms_datetime_date_only():
    assert parse_lvms_datetime("15.08.2026") == datetime(2026, 8, 15, 0, 0)


def test_parse_lvms_datetime_invalid():
    with pytest.raises(ValueError):
        parse_lvms_datetime("not-a-date")

