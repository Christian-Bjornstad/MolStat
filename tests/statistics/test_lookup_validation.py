from pathlib import Path
import zipfile
from xml.etree import ElementTree

import pytest
import xlsxwriter

from molstat.statistics import load_lookup


def workbook(path: Path, rows, *, inline=False):
    with xlsxwriter.Workbook(path, {"constant_memory": inline}) as book:
        sheet = book.add_worksheet("Oppslag")
        for index, row in enumerate(rows):
            sheet.write_row(index, 0, row)
    return path


def test_sparse_lookup_cells_keep_their_columns(tmp_path):
    path = workbook(tmp_path / "lookup.xlsx", [
        ["Analyse", "Nukleinsyre", "Rapportgruppe", "Svarfrist"],
        ["SYNTHETIC-OU", None, "Gruppe", 21],
    ])
    assert load_lookup(path)["SYNTHETIC-OU"] == {
        "Analyse": "SYNTHETIC-OU", "Nukleinsyre": "",
        "Rapportgruppe": "Gruppe", "Svarfrist": "21",
    }


def test_lookup_follows_workbook_sheet_order(tmp_path):
    path = tmp_path / "ordered.xlsx"
    with xlsxwriter.Workbook(path) as book:
        book.add_worksheet("Andre").write_row(0, 0, ["Feil ark"])
        sheet = book.add_worksheet("Oppslag")
        sheet.write_row(0, 0, ["Analyse", "Rapportgruppe"])
        sheet.write_row(1, 0, ["SYNTHETIC-OU", "Gruppe"])
    with zipfile.ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    root = ElementTree.fromstring(members["xl/workbook.xml"])
    sheets = root.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets")
    sheets[:] = list(reversed(list(sheets)))
    members["xl/workbook.xml"] = ElementTree.tostring(root)
    with zipfile.ZipFile(path, "w") as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)
    assert load_lookup(path)["SYNTHETIC-OU"]["Rapportgruppe"] == "Gruppe"


@pytest.mark.parametrize("rows,message", [
    ([["Feil", "Rapportgruppe"], ["SYNTHETIC-OU", "Gruppe"]], "Analyse"),
    ([["Analyse", "Rapportgruppe"], ["SYNTHETIC-OU", "A"], ["SYNTHETIC-OU", "B"]], "duplikat"),
    ([["Analyse", "Rapportgruppe", "Rapportgruppe"], ["SYNTHETIC-OU", "A", "B"]], "kolonnenavn"),
    ([["Analyse", "Rapportgruppe"]], "tom"),
    ([["Analyse", "Rapportgruppe"], [None, "Gruppe"]], "analyse"),
])
def test_invalid_lookup_reports_a_clear_error(tmp_path, rows, message):
    path = workbook(tmp_path / "lookup.xlsx", rows)
    with pytest.raises(ValueError, match=message):
        load_lookup(path)


def test_corrupt_lookup_is_a_configuration_error(tmp_path):
    path = tmp_path / "bad.xlsx"
    path.write_bytes(b"invalid workbook")
    with pytest.raises(ValueError, match="Lookup-filen"):
        load_lookup(path)


def test_inline_rich_text_lookup_preserves_full_label(tmp_path):
    path = tmp_path / "rich.xlsx"
    with xlsxwriter.Workbook(path, {"constant_memory": True}) as book:
        sheet = book.add_worksheet()
        sheet.write_row(0, 0, ["Analyse", "Rapportgruppe"])
        sheet.write_string(1, 0, "SYNTHETIC-OU")
        sheet.write_rich_string(1, 1, "Gruppe ", book.add_format({"bold": True}), "navn")
    assert load_lookup(path)["SYNTHETIC-OU"]["Rapportgruppe"] == "Gruppe navn"
