"""Generate the macro-free, read-only Excel view of the sample registry."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import xlsxwriter


def generate_compatibility_workbook(destination: Path) -> None:
    """Write a minimal target-engine compatibility workbook."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(path)
    try:
        workbook.set_calc_mode("auto")
        sheet = workbook.add_worksheet("Kompatibilitet")
        sheet.hide_gridlines(2)
        title = workbook.add_format(
            {"font_name": "Arial", "font_size": 14, "bold": True, "font_color": "#17365D"}
        )
        header = workbook.add_format(
            {
                "font_name": "Arial",
                "font_size": 10,
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#1F4E78",
                "align": "center",
                "valign": "vcenter",
            }
        )
        text = workbook.add_format(
            {
                "font_name": "Arial",
                "font_size": 10,
                "num_format": "@",
                "quote_prefix": True,
                "align": "left",
            }
        )
        timestamp = workbook.add_format(
            {"font_name": "Arial", "font_size": 10, "num_format": "yyyy-mm-dd hh:mm"}
        )
        sheet.write("A2", "Prøvesøk – kompatibilitetstest", title)
        sheet.write_row("A4", ["Felt", "Verdi"], header)
        sheet.write_string("A5", "Prøvenummer", text)
        sheet.write_string("B5", "00123456789012345678", text)
        sheet.write_string("A6", "MolStat-ID", text)
        sheet.write_string("B6", "MS-0000000000000001", text)
        sheet.write_string("A7", "Tidspunkt", text)
        sheet.write_datetime("B7", datetime(2026, 9, 10, 8, 15), timestamp)
        sheet.write_string("A8", "Formel", text)
        sheet.write_formula("B8", "=B6", text, "MS-0000000000000001")
        sheet.set_column("A:A", 18)
        sheet.set_column("B:B", 26)
        sheet.freeze_panes(4, 0)
    finally:
        workbook.close()
