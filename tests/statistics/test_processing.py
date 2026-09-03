from __future__ import annotations

import csv
import zipfile
from pathlib import Path

import pytest

from molstat.statistics import (
    ANTALL_COLUMNS,
    RESULTATER_COLUMNS,
    SOLIDE_ANTALL_COLUMNS,
    SOLIDE_RESULTATER_COLUMNS,
    build_antall,
    build_resultater,
    build_resultater_solide,
    clean_text,
    klassifiser_ekstraksjon,
    load_lookup,
    parse_tidspunkt,
    process_reports,
    read_lvms_csv,
)


def write_raw(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="cp1252", newline="") as f:
        csv.writer(f, delimiter=";").writerows(rows)


def make_lookup(tmp_path: Path) -> Path:
    """Minimal xlsx with one sheet: Analyse/Nukleinsyre/Rapportgruppe/Svarfrist."""
    path = tmp_path / "lookup.xlsx"
    content_types = (
        '<?xml version="1.0"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook = (
        '<?xml version="1.0"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        "</Relationships>"
    )
    strings = [
        "Analyse", "Nukleinsyre", "Rapportgruppe", "Svarfrist",
        "CALR-OU", "DNA", "MPN", "21",
    ]
    shared = (
        '<?xml version="1.0"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + "".join(
            f'<si><t>{value}</t></si>' for value in strings
        )
        + "</sst>"
    )
    sheet = (
        '<?xml version="1.0"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        '<row r="1"><c t="s"><v>0</v></c><c t="s"><v>1</v></c><c t="s"><v>2</v></c><c t="s"><v>3</v></c></row>'
        '<row r="2"><c t="s"><v>4</v></c><c t="s"><v>5</v></c><c t="s"><v>6</v></c><c t="s"><v>7</v></c></row>'
        "</sheetData></worksheet>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/sharedStrings.xml", shared)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


def test_clean_text_strips_t_wrapper_and_quotes() -> None:
    assert clean_text('=T("23OUM00210")') == "23OUM00210"
    assert clean_text('"bare quotes"') == "bare quotes"
    assert clean_text("") == ""


def test_parse_tidspunkt_formats() -> None:
    from datetime import datetime

    assert parse_tidspunkt("08.11.2023 13:29") == datetime(2023, 11, 8, 13, 29)
    assert parse_tidspunkt("24.10.2023") == datetime(2023, 10, 24)
    assert parse_tidspunkt("") is None
    assert parse_tidspunkt("not a date") is None


def test_klassifiser() -> None:
    assert klassifiser_ekstraksjon('=T("EKSTRAQIACRNA-H-OU")') == "RNA"
    assert klassifiser_ekstraksjon("EKSTRAAPKOL-H-OU") == "DNA"
    assert klassifiser_ekstraksjon("EKSTRAFFPEKOL-H-OU") == "DNA"
    assert klassifiser_ekstraksjon("EKSTRAEZ1VEV-H-OU") == "Ukjent/generell"


def test_best_extraction_priority(tmp_path: Path) -> None:
    from molstat.statistics import _best_extraction
    from datetime import datetime

    godk = datetime(2024, 3, 22, 13, 34)
    extractions = [
        {"nukleinsyre": "DNA", "ferdig": datetime(2024, 3, 13, 12, 2), "bestilling": None},
        {"nukleinsyre": "RNA", "ferdig": datetime(2024, 3, 20, 10, 0), "bestilling": None},
    ]
    chosen = _best_extraction("S1", "RNA", godk, extractions)
    assert chosen is not None and chosen["nukleinsyre"] == "RNA"

    # no candidate before godkjenning
    late = [{"nukleinsyre": "RNA", "ferdig": datetime(2024, 4, 1), "bestilling": None}]
    assert _best_extraction("S1", "RNA", godk, late) is None


def test_process_reports_golden_flow(tmp_path: Path) -> None:
    lookup_path = make_lookup(tmp_path)

    antall_csv = tmp_path / "raw" / "PAT-DIT-ANTALL-OU__a__b.csv"
    write_raw(
        antall_csv,
        [
            ["Sample ID", "Analyse", "Tidspunkt prøvetaking",
             "Tidspunkt opprettet", "Tidspunkt analysebestilling"],
            ['=T("S1")', '=T("CALR-OU")', "01.01.2024 08:00",
             "02.01.2024 09:00", "03.01.2024 10:00"],
            ['=T("S2")', '=T("UKJENT-KODE-OU")', "", "", ""],
        ],
    )

    resultater_csv = tmp_path / "raw" / "PAT-DIT-RESULTATER-OU__a__b.csv"
    write_raw(
        resultater_csv,
        [
            ["Sample ID", "Analyse", "Materiale", "Tidspunkt prøvetaking",
             "Tidspunkt opprettet", "Tidspunkt analysebestilling",
             "Tidspunkt analyseresultat", "Tidspunkt godkjenning"],
            ['=T("S1")', '=T("CALR-OU")', "B", "01.01.2024 08:00",
             "02.01.2024 09:00", "03.01.2024 10:00",
             "10.01.2024 12:00", "11.01.2024 08:30"],
        ],
    )

    ekstraksjon_csv = tmp_path / "raw" / "PAT-DIT-EKSTRAKSJON-OU__a__b.csv"
    write_raw(
        ekstraksjon_csv,
        [
            ["Sample ID", "Analyse", "Tidspunkt analysebestilling",
             "Tidspunkt analyseresultat", "Tidspunkt godkjenning"],
            ['=T("S1")', '=T("EKSTRAAPKOL-H-OU")', "05.01.2024 07:00",
             "06.01.2024 09:00", "06.01.2024 10:00"],
            # after godkjenning - must not match
            ['=T("S1")', '=T("EKSTRAAPKOL-H-OU")', "20.01.2024 07:00",
             "21.01.2024 09:00", "21.01.2024 10:00"],
        ],
    )

    out_dir = tmp_path / "prosessert"
    counts = process_reports(
        antall_csv, resultater_csv, ekstraksjon_csv, lookup_path, out_dir
    )
    assert counts == {"antall": 2, "resultater": 1}

    antall_rows = list(
        csv.DictReader(open(out_dir / "antall.csv", encoding="utf-8-sig"), delimiter=";")
    )
    assert antall_rows[0]["Nukleinsyre"] == "DNA"
    assert antall_rows[0]["Rapportgruppe"] == "MPN"
    assert antall_rows[0]["Maaned"] == "1"
    assert antall_rows[1]["Nukleinsyre"] == ""

    res_rows = list(
        csv.DictReader(open(out_dir / "resultater.csv", encoding="utf-8-sig"), delimiter=";")
    )
    row = res_rows[0]
    assert row["Ekstraksjon.ferdig"] == "2024/01/06 09:00:00"
    assert row["Svarfrist"] == "21"

    # BOM present (write_excel_csv2 behaviour)
    raw_bytes = (out_dir / "resultater.csv").read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")


def test_read_lvms_csv_normalises_headers_and_wrappers(tmp_path: Path) -> None:
    p = tmp_path / "r.csv"
    write_raw(
        p,
        [["Sample ID", "Analyse"], ['=T("S1")', '"CALR"']],
    )
    rows = read_lvms_csv(p)
    assert rows[0]["Sample.ID"] == "S1"
    assert rows[0]["Analyse"] == "CALR"


def test_load_lookup_reads_shared_strings(tmp_path: Path) -> None:
    lookup = load_lookup(make_lookup(tmp_path))
    assert lookup["CALR-OU"]["Nukleinsyre"] == "DNA"


# --- solide profile ----------------------------------------------------


def test_build_resultater_solide_picks_latest_finished_before_approval() -> None:
    results = [
        {
            "Sample.ID": "S1",
            "Analyse": "KRAS-VAR-OU",
            "Materiale": "Plasma",
            "Tidspunkt.prøvetaking": "01.01.2024",
            "Tidspunkt.opprettet": "02.01.2024 10:00",
            "Tidspunkt.analysebestilling": "03.01.2024 09:00",
            "Tidspunkt.analyseresultat": "06.01.2024 12:00",
            "Tidspunkt.godkjenning": "08.01.2024 08:00",
        }
    ]
    extractions = [
        # later finished but after approval - must NOT be chosen
        {"Sample.ID": "S1", "Analyse": "EKSTRAKSJON-SO-OU",
         "Tidspunkt.analysebestilling": "04.01.2024 09:00",
         "Tidspunkt.analyseresultat": "09.01.2024 10:00"},
        # latest finished BEFORE approval -> the answer
        {"Sample.ID": "S1", "Analyse": "EKSTRAKSJON-SO-OU",
         "Tidspunkt.analysebestilling": "03.01.2024 12:00",
         "Tidspunkt.analyseresultat": "05.01.2024 14:30"},
        # earlier candidate, must lose to the one above
        {"Sample.ID": "S1", "Analyse": "EKSTRAKSJON-SO-OU",
         "Tidspunkt.analysebestilling": "03.01.2024 07:00",
         "Tidspunkt.analyseresultat": "04.01.2024 11:00"},
    ]
    lookup = {"KRAS-VAR-OU": {"Rapportgruppe": "Solide tumorer", "Svarfrist": "7"}}
    rows = build_resultater_solide(results, extractions, lookup)
    assert len(rows) == 1
    row = rows[0]
    assert row["Ekstraksjon.ferdig"] == "2024/01/05 14:30:00"
    assert row["Ekstraksjon.Analyse"] == "EKSTRAKSJON-SO-OU"
    assert row["Ekstraksjon.analysebestilling"] == "2024/01/03 12:00:00"
    # start = max(bestilling, ekstraksjon ferdig)
    assert row["Starttid.svartid"] == "2024/01/05 14:30:00"
    assert row["Rapportgruppe"] == "Solide tumorer"
    assert row["Svarfrist"] == "7"


def test_build_antall_solide_has_no_nucleic_acid_column() -> None:
    rows = [
        {
            "Sample.ID": "S1",
            "Analyse": "KRAS-VAR-OU",
            "Tidspunkt.opprettet": "02.01.2024 10:00",
            "Tidspunkt.analysebestilling": "03.01.2024 09:00",
        }
    ]
    lookup = {"KRAS-VAR-OU": {"Rapportgruppe": "Solide tumorer", "Svarfrist": "7"}}
    antall = build_antall(rows, lookup)
    assert set(antall[0]) == set(SOLIDE_ANTALL_COLUMNS) | {"Nukleinsyre"}
    assert antall[0]["Svarfrist"] == "7"


def test_process_reports_solide_writes_13_column_export(tmp_path: Path) -> None:
    def raw_rows(header: list[str], data: list[list[str]]) -> Path:
        p = tmp_path / f"{header[0]}.csv"
        write_raw(p, [header, *data])
        return p

    res_header = [
        "Sample ID", "Analyse", "Materiale", "Tidspunkt prøvetaking",
        "Tidspunkt opprettet", "Tidspunkt analysebestilling",
        "Tidspunkt analyseresultat", "Tidspunkt godkjenning",
    ]
    ext_header = [
        "Sample ID", "Analyse", "Tidspunkt analysebestilling",
        "Tidspunkt analyseresultat",
    ]
    ant_header = [
        "Sample ID", "Analyse", "Tidspunkt prøvetaking",
        "Tidspunkt opprettet", "Tidspunkt analysebestilling",
        "Workitemgruppe", "Status prelgruppe",
    ]
    lookup = make_lookup(tmp_path)
    antall_path = raw_rows(
        ant_header,
        [['=T("S1")', '"KRAS-VAR-OU"', "01.01.2024", "02.01.2024 10:00",
          "03.01.2024 09:00", '=T("OU-SOLIDE")', '=T("Reported")']],
    )
    resultater_path = raw_rows(
        res_header,
        [['=T("S1")', '"KRAS-VAR-OU"', '"Plasma"', "01.01.2024",
          "02.01.2024 10:00", "03.01.2024 09:00", "06.01.2024 12:00",
          "08.01.2024 08:00"]],
    )
    ekstraksjon_path = raw_rows(
        ext_header,
        [['=T("S1")', '"EKSTRAKSJON-SO-OU"', "03.01.2024 12:00",
          "05.01.2024 14:30"]],
    )
    counts = process_reports(
        antall_path,
        resultater_path,
        ekstraksjon_path,
        lookup,
        tmp_path / "ut",
        profile="solide",
    )
    assert counts == {"antall": 1, "resultater": 1}
    with open(
        tmp_path / "ut" / "resultater.csv", encoding="utf-8-sig"
    ) as handle:
        header = next(csv.reader(handle, delimiter=";"))
    assert list(header) == list(SOLIDE_RESULTATER_COLUMNS)

