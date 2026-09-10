from datetime import datetime
from pathlib import Path

import pytest

from molstat.excel_search import (
    WorkbookValidationError,
    generate_search_workbook,
    publish_search_workbook,
    read_excel_snapshot,
    validate_search_workbook,
)

from .helpers import populated_database


def _snapshot(tmp_path: Path):
    return read_excel_snapshot(
        populated_database(tmp_path / "molstat.sqlite3"),
        generated_at=datetime(2026, 9, 10, 12, 30),
    )


def test_valid_candidate_atomically_replaces_previous_workbook(tmp_path: Path) -> None:
    destination = tmp_path / "Prøvesøk.xlsx"
    destination.write_bytes(b"previous")

    result = publish_search_workbook(_snapshot(tmp_path), destination)

    assert result.status == "published"
    assert destination.read_bytes().startswith(b"PK")
    assert validate_search_workbook(destination) is None
    assert list(tmp_path.glob(".Prøvesøk.*.pending.xlsx")) == []


def test_invalid_candidate_never_replaces_previous_workbook(tmp_path: Path) -> None:
    destination = tmp_path / "Prøvesøk.xlsx"
    destination.write_bytes(b"previous")

    def reject(_path: Path) -> None:
        raise WorkbookValidationError("synthetic validation failure")

    with pytest.raises(WorkbookValidationError):
        publish_search_workbook(_snapshot(tmp_path), destination, validate=reject)

    assert destination.read_bytes() == b"previous"
    assert list(tmp_path.glob(".Prøvesøk.*.pending.xlsx")) == []


def test_locked_target_keeps_previous_workbook_and_returns_retry_status(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "Prøvesøk.xlsx"
    destination.write_bytes(b"previous")

    def locked(_source: Path, _destination: Path) -> None:
        raise PermissionError("synthetic lock")

    result = publish_search_workbook(
        _snapshot(tmp_path),
        destination,
        replace=locked,
    )

    assert result.status == "locked"
    assert destination.read_bytes() == b"previous"
    assert list(tmp_path.glob(".Prøvesøk.*.pending.xlsx")) == []
