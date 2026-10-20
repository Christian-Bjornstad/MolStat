from pathlib import Path
import zipfile

from molstat.excel_search import generate_compatibility_workbook


def test_xlsx_generator_preserves_text_dates_and_formula_contract(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "Prøvesøk.xlsx"

    generate_compatibility_workbook(destination)

    assert destination.is_file()
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
    assert "xl/vbaProject.bin" not in names
    assert "calcMode=\"manual\"" not in workbook_xml
    assert "fullCalcOnLoad=\"1\"" in workbook_xml
    assert "00123456789012345678" in shared_strings
    assert "M-000001" in shared_strings
    assert "2026-09-10T08:15:00" not in shared_strings
    assert "<f>" in sheet_xml
    assert "<v>" in sheet_xml
