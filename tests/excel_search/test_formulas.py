from datetime import datetime
from pathlib import Path
import zipfile

from molstat.excel_search import (
    generate_search_workbook,
    read_excel_snapshot,
    search_samples,
    select_unique_sample,
)

from .helpers import populated_database


def test_search_semantics_cover_blank_exact_prefix_and_unique_selection(
    tmp_path: Path,
) -> None:
    snapshot = read_excel_snapshot(
        populated_database(tmp_path / "molstat.sqlite3"),
        generated_at=datetime(2026, 9, 10, 12, 30),
    )
    molstat_key = snapshot.samples[0].molstat_key

    assert search_samples(snapshot.samples, "", prefix=False) == ()
    assert search_samples(snapshot.samples, "00123456789012345678", prefix=False)
    assert search_samples(snapshot.samples, molstat_key.lower(), prefix=False)
    assert search_samples(snapshot.samples, "001234", prefix=True)
    assert search_samples(snapshot.samples, "001234", prefix=False) == ()
    assert select_unique_sample(snapshot.samples, "001234", prefix=True) == molstat_key


def test_workbook_contains_dynamic_search_and_detail_formulas(tmp_path: Path) -> None:
    snapshot = read_excel_snapshot(
        populated_database(tmp_path / "molstat.sqlite3"),
        generated_at=datetime(2026, 9, 10, 12, 30),
    )
    destination = tmp_path / "Prøvesøk.xlsx"

    generate_search_workbook(snapshot, destination)

    with zipfile.ZipFile(destination) as archive:
        search_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        formula_xml = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.startswith("xl/worksheets/sheet")
        )
    assert "FILTER" in search_xml
    assert "Prøver" in search_xml
    assert "Analyser" in search_xml
    assert "Ingen treff" in search_xml or "Ingen analyser" in search_xml
    assert "dataValidation" in search_xml
    assert 'ref="D5"' in search_xml
    assert 'ref="K5"' in search_xml
    assert "$A$5:$A$54" in search_xml
    assert "COUNTIF" in formula_xml
