from __future__ import annotations
from unit_fixtures import analysis_codes

import csv
import zipfile
from pathlib import Path

import pytest

from molstat.statistics import (
    ANTALL_COLUMNS,
    RESULTATER_COLUMNS,
    SOLIDE_ANTALL_COLUMNS,
    SOLIDE_RESULTATER_COLUMNS,
    StatisticsProcessor,
    _report_archives,
    build_antall,
    build_resultater,
    build_resultater_solide,
    clean_text,
    klassifiser_ekstraksjon,
    parse_tidspunkt,
    process_reports,
    read_lvms_csv,
)


def write_raw(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="cp1252", newline="") as f:
        csv.writer(f, delimiter=";").writerows(rows)


def make_lookup(tmp_path):
    return {"CALR-OU", "KRAS-VAR-OU"}


def test_report_archives_include_old_and_new_intervals(tmp_path: Path) -> None:
    archive = tmp_path / "raw" / "statistics" / "hemato"
    archive.mkdir(parents=True)
    old = archive / "PAT-DIT-ANTALL-OU__2024-01-01__2026-09-04.csv"
    new = archive / "PAT-DIT-ANTALL-OU__2026-09-05__2026-09-07.csv"
    other = archive / "PAT-DIT-RESULTATER-OU__2026-09-05__2026-09-07.csv"
    for path in (old, new, other):
        path.write_text("A;B\n1;2\n", encoding="cp1252")

    assert _report_archives(new) == (old, new)


def test_statistics_processor_merges_complete_archive_before_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "raw" / "statistics" / "hemato"
    captured: dict[str, list[str]] = {}
    current: list[Path] = []
    for marker in ("ANTALL", "RESULTATER", "EKSTRAKSJON"):
        old = archive / f"PAT-DIT-{marker}-OU__2024-01-01__2026-09-04.csv"
        new = archive / f"PAT-DIT-{marker}-OU__2026-09-05__2026-09-07.csv"
        write_raw(old, [["Sample ID", "Analyse"], ["old", marker], ["overlap", marker]])
        write_raw(new, [["Sample ID", "Analyse"], ["overlap", marker], ["new", marker]])
        current.append(new)

    def record_inputs(
        ordered: Path,
        answered: Path,
        extraction: Path,
        lookup_path: Path,
        output_dir: Path,
        *,
        profile: str,
        molstat_ids: Mapping[str, str],
    ) -> dict[str, int]:
        del lookup_path, profile, molstat_ids
        for marker, path in zip(
            ("ANTALL", "RESULTATER", "EKSTRAKSJON"),
            (ordered, answered, extraction),
            strict=True,
        ):
            captured[marker] = [row["Sample ID"] for row in csv.DictReader(
                path.open(encoding="cp1252"), delimiter=";"
            )]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "antall.csv").write_text("Analyse\n", encoding="utf-8")
        (output_dir / "resultater.csv").write_text("Analyse\n", encoding="utf-8")
        return {"antall": 3, "resultater": 3}

    monkeypatch.setattr("molstat.statistics.process_reports", record_inputs)
    output_dir = tmp_path / "processed"

    result = StatisticsProcessor(analysis_codes=analysis_codes("hemato")).process(
        "hemato", current, output_dir
    )

    assert captured == {
        "ANTALL": ["old", "overlap", "new"],
        "RESULTATER": ["old", "overlap", "new"],
        "EKSTRAKSJON": ["old", "overlap", "new"],
    }
    assert result.antall == output_dir / "antall.csv"
    assert result.resultater == output_dir / "resultater.csv"


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


def test_best_extraction_prefers_generic_then_latest_completion() -> None:
    from datetime import datetime
    from molstat.statistics import _best_extraction

    candidates = [
        {"nukleinsyre": "DNA", "ferdig": datetime(2026, 9, 24)},
        {"nukleinsyre": "Ukjent/generell", "ferdig": datetime(2026, 9, 23)},
        {"nukleinsyre": "Ukjent/generell", "ferdig": datetime(2026, 9, 22)},
    ]
    chosen = _best_extraction("SYNTHETIC", "RNA", datetime(2026, 9, 25), candidates)
    assert chosen["nukleinsyre"] == "Ukjent/generell"
    assert chosen["ferdig"] == datetime(2026, 9, 23)




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
        antall_csv,
        resultater_csv,
        ekstraksjon_csv,
        lookup_path,
        out_dir,
        molstat_ids={"S1": "M-000001"},
    )
    assert counts == {"antall": 1, "resultater": 1}

    antall_rows = list(
        csv.DictReader(open(out_dir / "antall.csv", encoding="utf-8-sig"), delimiter=";")
    )
    assert antall_rows[0]["Nukleinsyre"] == ""
    assert antall_rows[0]["Rapportgruppe"] == ""
    assert antall_rows[0]["Maaned"] == "1"
    assert len(antall_rows) == 1  # Unconfigured code is filtered by JSON.

    res_rows = list(
        csv.DictReader(open(out_dir / "resultater.csv", encoding="utf-8-sig"), delimiter=";")
    )
    row = res_rows[0]
    assert row["MolStat-ID"] == "M-000001"
    assert row["Ekstraksjon.ferdig"] == "2024/01/06 09:00:00"
    assert row["Svarfrist"] == ""

    # BOM present (write_excel_csv2 behaviour)
    raw_bytes = (out_dir / "resultater.csv").read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")
    assert "MolStat-ID" not in antall_rows[0]


def test_read_lvms_csv_normalises_headers_and_wrappers(tmp_path: Path) -> None:
    p = tmp_path / "r.csv"
    write_raw(
        p,
        [["Sample ID", "Analyse"], ['=T("S1")', '"CALR"']],
    )
    rows = read_lvms_csv(p)
    assert rows[0]["Sample.ID"] == "S1"
    assert rows[0]["Analyse"] == "CALR"




# --- solide profile ----------------------------------------------------


def test_build_resultater_solide_keeps_lookup_values() -> None:
    results = [{"Sample.ID": "S1", "Analyse": "TERT-OU",
                "Tidspunkt.analyseresultat": "06.01.2024 12:00"}]
    extractions = [{"Sample.ID": "S1", "Analyse": "EKSTRAKSJON-OU",
                    "Analyseresultat": "Maxwell DNA",
                    "Tidspunkt.analyseresultat": "03.01.2024 12:00",
                    "Tidspunkt.godkjenning": "05.01.2024 14:30"}]
    lookup = {"TERT-OU": {"Rapportgruppe": "Sanger", "Svarfrist": "15"}}
    row = build_resultater_solide(results, extractions, lookup)[0]
    assert row["Ekstraksjon.valgt"] == "2024/01/03 12:00:00"
    assert row["Ekstraksjon.ferdig"] == "2024/01/05 14:30:00"
    assert row["Starttid.svartid"] == row["Ekstraksjon.ferdig"]
    assert row["Rapportgruppe"] == "Sanger"
    assert row["Svarfrist"] == "15"


def test_result_export_fails_closed_when_registry_mapping_is_missing() -> None:
    results = [
        {
            "Sample.ID": "S1",
            "Analyse": "CALR-OU",
            "Tidspunkt.godkjenning": "08.01.2024 08:00",
        }
    ]

    with pytest.raises(ValueError, match="MolStat-ID"):
        build_resultater(results, (), {}, molstat_ids={})


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


def test_process_reports_solide_writes_result_export_contract(tmp_path: Path) -> None:
    def raw_rows(header: list[str], data: list[list[str]]) -> Path:
        p = tmp_path / f"report-{len(list(tmp_path.glob('*.csv')))}.csv"
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
        [['=T("S1")', '"CALR-OU"', "01.01.2024", "02.01.2024 10:00",
          "03.01.2024 09:00", '=T("OU-SOLIDE")', '=T("Reported")']],
    )
    resultater_path = raw_rows(
        res_header,
        [['=T("S1")', '"CALR-OU"', '"Plasma"', "01.01.2024",
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

