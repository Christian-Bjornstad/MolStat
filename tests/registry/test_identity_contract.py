from datetime import datetime
from pathlib import Path

from molstat.registry import (
    build_occurrence_identity,
    load_identity_contract,
    normalize_identifier,
)


def test_repository_identity_contract_covers_every_lvms_source() -> None:
    root = Path(__file__).resolve().parents[2]

    contract = load_identity_contract(root / "config" / "identity-contract.json")

    assert contract.source_system == "LVMS"
    assert set(contract.reports) == {
        "backlog",
        "statistics_ordered",
        "statistics_answered",
        "statistics_extraction",
    }
    assert contract.reports["backlog"].occurrence_id_columns[0] == "WorkItem"
    assert contract.sample_number_scope == "source_system"


def test_identifier_normalization_preserves_leading_zeroes() -> None:
    assert normalize_identifier('=T(" 001234 ")') == "001234"
    assert normalize_identifier(" ab-12 ") == "AB-12"


def test_workitem_is_the_authoritative_occurrence_identity() -> None:
    first = build_occurrence_identity(
        source_system="LVMS",
        sample_number="00123",
        analysis_code="CALR-OU",
        ordered_at=datetime(2026, 9, 10, 8, 0),
        source_occurrence_id="WORK-1",
    )
    second = build_occurrence_identity(
        source_system="LVMS",
        sample_number="00123",
        analysis_code="CALR-OU",
        ordered_at=datetime(2026, 9, 10, 8, 0),
        source_occurrence_id="WORK-2",
    )

    assert first.key != second.key
    assert first.uses_fallback is False
    assert second.uses_fallback is False


def test_fallback_uses_order_time_and_is_marked_for_quality_review() -> None:
    first = build_occurrence_identity(
        source_system="LVMS",
        sample_number="S-1",
        analysis_code="CALR-OU",
        ordered_at=datetime(2026, 9, 10, 8, 0),
    )
    repeated = build_occurrence_identity(
        source_system="LVMS",
        sample_number="S-1",
        analysis_code="CALR-OU",
        ordered_at=datetime(2026, 9, 10, 9, 0),
    )

    assert first.key != repeated.key
    assert first.uses_fallback is True
    assert repeated.uses_fallback is True


def test_identity_key_never_contains_sensitive_source_values() -> None:
    identity = build_occurrence_identity(
        source_system="LVMS",
        sample_number="SECRET-SAMPLE-42",
        analysis_code="CALR-OU",
        ordered_at=datetime(2026, 9, 10, 8, 0),
        source_occurrence_id="SECRET-WORKITEM-7",
    )

    assert "SECRET" not in identity.key
    assert len(identity.key) == 64
