import csv
from pathlib import Path
import re

import pytest

from molstat.publisher import (
    PrivacyViolation,
    PublicationPolicy,
    SharePointPublisher,
)


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _publisher() -> SharePointPublisher:
    return SharePointPublisher(
        PublicationPolicy(
            allowed_columns={
                "resultater.csv": frozenset({"Analyse", "Rapportgruppe"}),
            },
            forbidden_patterns=(
                re.compile(r"pasient", re.IGNORECASE),
                re.compile(r"sample[ ._-]*id", re.IGNORECASE),
                re.compile(r"prøve[ ._-]*id", re.IGNORECASE),
            ),
        )
    )


def test_publisher_rejects_patient_identifier_column(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path / "bad.csv",
        ["Analyse", "Pasientnummer"],
        [["A", "123"]],
    )

    with pytest.raises(PrivacyViolation, match="resultater.csv"):
        _publisher().publish(
            {"resultater.csv": source}, tmp_path / "sharepoint"
        )


def test_failed_validation_preserves_last_publication(tmp_path: Path) -> None:
    destination = tmp_path / "sharepoint"
    destination.mkdir()
    published = destination / "resultater.csv"
    published.write_text("old", encoding="utf-8")
    bad_source = _write_csv(
        tmp_path / "bad.csv",
        ["Analyse", "Sample ID"],
        [["A", "SECRET"]],
    )

    with pytest.raises(PrivacyViolation):
        _publisher().publish({"resultater.csv": bad_source}, destination)

    assert published.read_text(encoding="utf-8") == "old"


def test_safe_publication_is_complete_and_reports_digest(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path / "safe.csv",
        ["Analyse", "Rapportgruppe"],
        [["CALR-OU", "MPN"]],
    )
    destination = tmp_path / "sharepoint"

    result = _publisher().publish({"resultater.csv": source}, destination)

    target = destination / "resultater.csv"
    assert target.read_bytes() == source.read_bytes()
    assert result.files["resultater.csv"].path == target
    assert len(result.files["resultater.csv"].sha256) == 64
    assert not list(destination.glob("*.tmp"))


def test_publisher_requires_exact_allowlisted_file_set(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "safe.csv", ["Analyse"], [["CALR-OU"]])

    with pytest.raises(PrivacyViolation, match="filsett"):
        _publisher().publish({"unexpected.csv": source}, tmp_path / "sharepoint")
