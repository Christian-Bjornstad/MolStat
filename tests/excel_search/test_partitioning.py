from datetime import datetime
from pathlib import Path
import zipfile
from xml.etree import ElementTree

import pytest

from molstat.excel_search import (
    ExcelAnalysisRow,
    ExcelSnapshot,
    generate_search_workbook,
    partition_analysis_rows,
)


def _analysis(year: int, sequence: int) -> ExcelAnalysisRow:
    return ExcelAnalysisRow(
        molstat_key=f"MS-{year}-{sequence}",
        sample_number=f"S-{year}-{sequence}",
        analysis_code="CALR-OU",
        ordered_at=datetime(year, 1, 1, 8, sequence),
        in_backlog=False,
        source_kinds="statistics_answered",
        resulted_at=None,
        approved_at=None,
    )


def test_row_guard_partitions_by_year_and_formula_references_every_table(
    tmp_path: Path,
) -> None:
    rows = tuple(
        _analysis(year, sequence)
        for year in (2024, 2025)
        for sequence in range(2)
    )
    partitions = partition_analysis_rows(rows, row_limit=2)
    assert tuple(partitions) == ("Analyser 2024", "Analyser 2025")

    snapshot = ExcelSnapshot(datetime(2026, 9, 10, 12, 30), (), rows)
    destination = tmp_path / "Prøvesøk.xlsx"
    generate_search_workbook(snapshot, destination, analysis_row_limit=2)

    with zipfile.ZipFile(destination) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        search_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        table_xml = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.startswith("xl/tables/table")
        )
    assert 'name="Analyser 2024"' in workbook_xml
    assert 'name="Analyser 2025"' in workbook_xml
    assert 'name="tblAnalyser2024"' in table_xml
    assert 'name="tblAnalyser2025"' in table_xml
    assert "Analyser 2024" in search_xml
    assert "Analyser 2025" in search_xml


def test_partitioned_search_filters_before_stacking(tmp_path):
    rows = (_analysis(2024, 1), _analysis(2025, 1))
    destination = tmp_path / "search.xlsx"
    generate_search_workbook(ExcelSnapshot(datetime(2026, 9, 10), (), rows),
                             destination, analysis_row_limit=1)
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(destination) as archive:
        root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    formula = root.find(f".//{namespace}c[@r='K5']/{namespace}f").text
    assert "_xlfn.VSTACK(_xlfn._xlws.FILTER(IF(" in formula
    assert '_xlfn.LET(_xlpm.matches,' in formula
    assert 'INDEX(_xlpm.matches,0,1)<>""' in formula


@pytest.mark.parametrize("limit", [0, -1, True, 1_048_576])
def test_row_limit_cannot_exceed_excel_capacity(limit):
    with pytest.raises(ValueError):
        partition_analysis_rows((), row_limit=limit)
