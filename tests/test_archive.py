from datetime import date
from pathlib import Path

from molstat.archive import RawArchive
from molstat.lvms.report import ReportRequest


def _request() -> ReportRequest:
    return ReportRequest(
        kind="backlog",
        unit="hemato",
        report_name="PAT-DIT-RESTANSE-OU",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 2),
    )


def test_archive_keeps_source_and_never_overwrites_existing_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "download.csv"
    source.write_bytes(b"first")
    archive = RawArchive(tmp_path / "sensitive")

    first = archive.store(source, _request())
    source.write_bytes(b"second")
    second = archive.store(source, _request())

    assert source.read_bytes() == b"second"
    assert first.path.read_bytes() == b"first"
    assert second.path.read_bytes() == b"second"
    assert first.path.name == "PAT-DIT-RESTANSE-OU__2026-09-01__2026-09-02.csv"
    assert second.path.name == "PAT-DIT-RESTANSE-OU__2026-09-01__2026-09-02__r2.csv"
    assert first.sha256 != second.sha256


def test_archive_uses_kind_and_unit_boundaries(tmp_path: Path) -> None:
    source = tmp_path / "download.csv"
    source.write_text("content", encoding="utf-8")

    result = RawArchive(tmp_path / "sensitive").store(source, _request())

    assert result.path.parent == (
        tmp_path / "sensitive" / "raw" / "backlog" / "hemato"
    )
