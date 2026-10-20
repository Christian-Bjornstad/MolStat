from datetime import datetime
from pathlib import Path
import zipfile
from xml.etree import ElementTree

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


def test_search_formulas_use_xlsx_spilled_range_serialization(tmp_path):
    snapshot = read_excel_snapshot(populated_database(tmp_path / "data.sqlite3"),
                                   generated_at=datetime(2026, 9, 10))
    path = tmp_path / "search.xlsx"
    generate_search_workbook(snapshot, path)
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    formulas = " ".join(element.text or "" for element in root.iter(
        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}f"))
    assert "$D$5#" not in formulas
    assert "_xlfn.ANCHORARRAY($D$5)" in formulas
    # FILTER turns empty source cells into 0 unless the data range explicitly
    # returns empty text. Date columns would otherwise display January 1900.
    assert 'IF(\'Analyser\'!$A$2:$H$3="","",\'Analyser\'!$A$2:$H$3)' in formulas


def test_prefix_matching_ignores_whitespace_only_searches(tmp_path):
    snapshot = read_excel_snapshot(populated_database(tmp_path / "data.sqlite3"),
                                   generated_at=datetime(2026, 9, 10))
    path = tmp_path / "search.xlsx"
    generate_search_workbook(snapshot, path)
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("xl/worksheets/sheet2.xml"))
    formula = root.find(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}f").text
    assert 'TRIM(\'Prøvesøk\'!$A$5:$A$54)<>""' in formula


def test_spilled_results_columns_use_date_formats(tmp_path):
    snapshot = read_excel_snapshot(populated_database(tmp_path / "data.sqlite3"),
                                   generated_at=datetime(2026, 9, 10))
    path = tmp_path / "search.xlsx"
    generate_search_workbook(snapshot, path)
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        styles = ElementTree.fromstring(archive.read("xl/styles.xml"))
    date_ids = {item.get("numFmtId") for item in styles.findall(f"{namespace}numFmts/{namespace}numFmt")
                if item.get("formatCode") == "yyyy-mm-dd hh:mm"}
    formats = list(styles.find(f"{namespace}cellXfs"))
    for column in (6, 7, 14, 17, 18):
        definition = next(item for item in sheet.findall(f"{namespace}cols/{namespace}col")
                          if int(item.get("min")) <= column <= int(item.get("max")))
        assert formats[int(definition.get("style", "0"))].get("numFmtId") in date_ids
