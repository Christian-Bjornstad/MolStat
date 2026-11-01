from datetime import datetime
from pathlib import Path
import zipfile
from xml.etree import ElementTree

from molstat.excel_search import generate_search_workbook, read_excel_snapshot

from .helpers import populated_database


def test_workbook_has_expected_sheets_tables_and_typed_values(tmp_path: Path) -> None:
    database = populated_database(tmp_path / "molstat.sqlite3")
    snapshot = read_excel_snapshot(
        database,
        generated_at=datetime(2026, 9, 10, 12, 30),
    )
    destination = tmp_path / "Prøvesøk.xlsx"

    generate_search_workbook(snapshot, destination)

    with zipfile.ZipFile(destination) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        sheet_names = [
            name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")
        ]
        table_xml = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.startswith("xl/tables/table")
        )
        all_sheets = "\n".join(
            archive.read(name).decode("utf-8") for name in sheet_names
        )
        shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
    assert [workbook_xml.index(f'name="{name}"') for name in (
        "Prøvesøk", "Prøver", "Analyser", "Om"
    )] == sorted(workbook_xml.index(f'name="{name}"') for name in (
        "Prøvesøk", "Prøver", "Analyser", "Om"
    ))
    assert 'name="tblProver"' in table_xml
    assert 'name="tblAnalyser"' in table_xml
    assert "00123456789012345678" in shared_strings
    assert "WorkItem" not in shared_strings
    assert "Identitetsstatus" not in shared_strings
    assert "2026-09-08T08:00:00" not in shared_strings
    assert "<pane" in all_sheets


def test_workbook_locks_structure_data_and_formulas_but_allows_search_inputs(tmp_path):
    snapshot = read_excel_snapshot(populated_database(tmp_path / 'data.sqlite3'),
                                   generated_at=datetime(2026, 11, 1))
    path = tmp_path / 'search.xlsx'
    generate_search_workbook(snapshot, path)
    ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    with zipfile.ZipFile(path) as archive:
        workbook = ElementTree.fromstring(archive.read('xl/workbook.xml'))
        styles = ElementTree.fromstring(archive.read('xl/styles.xml')).find(f'{ns}cellXfs')
        sheets = [ElementTree.fromstring(archive.read(name)) for name in archive.namelist()
                  if name.startswith('xl/worksheets/sheet') and name.endswith('.xml')]
    assert workbook.find(f'{ns}workbookProtection').get('lockStructure') == '1'
    assert workbook.find(f'{ns}fileSharing').get('readOnlyRecommended') == '1'
    for sheet in sheets:
        assert sheet.find(f'{ns}sheetProtection').get('sheet') == '1'
        for cell in sheet.iter(f'{ns}c'):
            protection = styles[int(cell.get('s', '0'))].find(f'{ns}protection')
            unlocked = protection is not None and protection.get('locked') == '0'
            assert unlocked == (sheet is sheets[0] and cell.get('r') in {
                'B56', *(f'A{row}' for row in range(5, 55))})
