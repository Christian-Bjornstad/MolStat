import csv
import hashlib
import os
from pathlib import Path
import re

import pytest

from molstat._backlog.export import BACKLOG_PUBLIC_COLUMNS
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


def test_invalid_backlog_export_preserves_previous_public_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "sharepoint" / "Prøveflyt"
    destination.mkdir(parents=True)
    target = destination / "restansehistorikk.csv"
    previous = b"previous-valid-publication"
    target.write_bytes(previous)
    bad_source = _write_csv(
        tmp_path / "bad-backlog.csv",
        [*BACKLOG_PUBLIC_COLUMNS, "SampleID"],
        [[*("" for _ in BACKLOG_PUBLIC_COLUMNS), "PRIVATE-SYNTHETIC"]],
    )
    publisher = SharePointPublisher(
        PublicationPolicy(
            allowed_columns={
                "restansehistorikk.csv": frozenset(BACKLOG_PUBLIC_COLUMNS)
            },
            forbidden_patterns=(re.compile(r"sample[ ._-]*id", re.I),),
        )
    )

    with pytest.raises(PrivacyViolation):
        publisher.publish({"restansehistorikk.csv": bad_source}, destination)

    assert target.read_bytes() == previous


@pytest.mark.parametrize("locked_name", ["antall.csv", "resultater.csv"])
def test_backup_cleanup_failure_keeps_complete_new_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog, locked_name: str,
) -> None:
    destination = tmp_path / "sharepoint"
    destination.mkdir()
    files = {}
    for name in ("antall.csv", "resultater.csv"):
        (destination / name).write_text("previous", encoding="utf-8")
        files[name] = _write_csv(tmp_path / name, ["Analyse"], [["SYNTHETIC"]])
    publisher = SharePointPublisher(PublicationPolicy(
        {name: frozenset({"Analyse"}) for name in files}, (),
    ))
    original_unlink = Path.unlink

    def fail_locked_backup(path, *args, **kwargs):
        if path.suffix == ".bak" and path.name.startswith(f".{locked_name}."):
            raise PermissionError("Synthetic backup lock")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_locked_backup)

    result = publisher.publish(files, destination)

    for name, source in files.items():
        assert (destination / name).read_bytes() == source.read_bytes()
        assert result.files[name].sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert len(list(destination.glob("*.bak"))) == 1
    assert "backup" in caplog.text.lower()


def test_failed_second_install_restores_entire_previous_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "sharepoint"
    destination.mkdir()
    files = {}
    previous = {}
    for name in ("antall.csv", "resultater.csv"):
        previous[name] = f"previous {name}".encode()
        (destination / name).write_bytes(previous[name])
        files[name] = _write_csv(tmp_path / name, ["Analyse"], [["SYNTHETIC"]])
    publisher = SharePointPublisher(PublicationPolicy(
        {name: frozenset({"Analyse"}) for name in files}, (),
    ))
    original_replace = os.replace

    def fail_second_install(source, target):
        if Path(source).suffix == ".tmp" and Path(target).name == "resultater.csv":
            raise PermissionError("Synthetic install failure")
        return original_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_second_install)

    with pytest.raises(PermissionError, match="Synthetic install failure"):
        publisher.publish(files, destination)

    assert {name: (destination / name).read_bytes() for name in files} == previous
    assert not list(destination.glob("*.bak"))
    assert not list(destination.glob("*.tmp"))
