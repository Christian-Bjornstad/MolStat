from __future__ import annotations

import csv
import zipfile
from pathlib import Path

from molstat.statistics import find_report_archives, process_unit


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="cp1252", newline="") as f:
        csv.writer(f, delimiter=";").writerows(rows)


def make_lookup(tmp_path):
    return {"CALR-OU"}


def seed_archives(unit_dir: Path) -> None:
    raa = unit_dir / "raa"
    write_csv(
        raa / "PAT-DIT-ANTALL-OU__20240101__20240110.csv",
        [
            ["Sample ID", "Analyse", "Tidspunkt prøvetaking",
             "Tidspunkt opprettet", "Tidspunkt analysebestilling"],
            ['=T("S1")', '=T("CALR-OU")', "01.01.2024 08:00",
             "02.01.2024 09:00", "03.01.2024 10:00"],
        ],
    )
    # overlapping second window for the same report
    write_csv(
        raa / "PAT-DIT-ANTALL-OU__20240108__20240120.csv",
        [
            ["Sample ID", "Analyse", "Tidspunkt prøvetaking",
             "Tidspunkt opprettet", "Tidspunkt analysebestilling"],
            ['=T("S1")', '=T("CALR-OU")', "01.01.2024 08:00",
             "02.01.2024 09:00", "03.01.2024 10:00"],
            ['=T("S2")', '=T("CALR-OU")', "", "", ""],
        ],
    )
    resultater_header = [
        "Sample ID", "Analyse", "Materiale", "Tidspunkt prøvetaking",
        "Tidspunkt opprettet", "Tidspunkt analysebestilling",
        "Tidspunkt analyseresultat", "Tidspunkt godkjenning",
    ]
    write_csv(
        raa / "PAT-DIT-RESULTATER-OU__20240101__20240120.csv",
        [resultater_header,
         ['=T("S1")', '=T("CALR-OU")', "B", "01.01.2024 08:00",
          "02.01.2024 09:00", "03.01.2024 10:00",
          "10.01.2024 12:00", "11.01.2024 08:30"]],
    )
    write_csv(
        raa / "PAT-DIT-EKSTRAKSJON-OU__20240101__20240120.csv",
        [["Sample ID", "Analyse", "Tidspunkt analysebestilling",
          "Tidspunkt analyseresultat", "Tidspunkt godkjenning"],
         ['=T("S1")', '=T("EKSTRAAPKOL-H-OU")', "05.01.2024 07:00",
          "06.01.2024 09:00", "06.01.2024 10:00"]],
    )


def test_find_report_archives_matches_prefix(tmp_path: Path) -> None:
    seed_archives(tmp_path)
    found = find_report_archives(tmp_path / "raa", "PAT-DIT-ANTALL-OU")
    assert len(found) == 2
    assert all(p.name.startswith("PAT-DIT-ANTALL-OU__") for p in found)


def test_process_unit_merges_and_writes_prosessert(tmp_path: Path) -> None:
    seed_archives(tmp_path)
    outcome = process_unit(
        tmp_path,
        make_lookup(tmp_path),
        {
            "ordered": "PAT-DIT-ANTALL-OU",
            "answered": "PAT-DIT-RESULTATER-OU",
            "extraction": "PAT-DIT-EKSTRAKSJON-OU",
        },
    )
    assert outcome.merged_files == 3
    assert outcome.antall_rows == 2  # duplicate S1 dropped
    assert outcome.resultater_rows == 1

    antall = list(csv.DictReader(
        open(outcome.output_dir / "antall.csv", encoding="utf-8-sig"),
        delimiter=";",
    ))
    assert {row["Analyse"] for row in antall} == {"CALR-OU"}
    res = list(csv.DictReader(
        open(outcome.output_dir / "resultater.csv", encoding="utf-8-sig"),
        delimiter=";",
    ))
    assert res[0]["Ekstraksjon.ferdig"] == "2024/01/06 09:00:00"


def test_process_unit_without_resultat_archive_is_noop(tmp_path: Path) -> None:
    (tmp_path / "raa").mkdir(parents=True)
    write_csv(
        tmp_path / "raa" / "PAT-DIT-ANTALL-SO__20240101__20240110.csv",
        [["Sample ID"], ['=T("S1")']],
    )
    outcome = process_unit(
        tmp_path,
        make_lookup(tmp_path),
        {"ordered": "PAT-DIT-ANTALL-SO", "answered": ""},
    )
    assert outcome.antall_rows == 0 and outcome.merged_files == 1

