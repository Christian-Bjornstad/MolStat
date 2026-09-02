from __future__ import annotations

import csv
from pathlib import Path

from molstat.statistics import merge_report_csvs, write_merged_csv


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="cp1252", newline="") as f:
        csv.writer(f, delimiter=";").writerows(rows)


def test_merge_drops_duplicate_rows_from_overlapping_windows(tmp_path: Path) -> None:
    a = tmp_path / "REP__20240101__20240110.csv"
    write_csv(
        a,
        [
            ["Sample ID", "Analyse", "Tidspunkt opprettet"],
            ['=T("S1")', '=T("CALR-OU")', "01.01.2024 08:00"],
            ['=T("S2")', '=T("CALR-OU")', "02.01.2024 08:00"],
        ],
    )
    b = tmp_path / "REP__20240108__20240120.csv"
    write_csv(
        b,
        [
            ["Sample ID", "Analyse", "Tidspunkt opprettet"],
            # S2 duplicated by the overlap window
            ['=T("S2")', '=T("CALR-OU")', "02.01.2024 08:00"],
            ['=T("S3")', '=T("JAK2-EX12-OU")', "15.01.2024 09:00"],
        ],
    )
    header, rows = merge_report_csvs([a, b])
    assert header == ["Sample ID", "Analyse", "Tidspunkt opprettet"]
    samples = sorted(row["Sample ID"] for row in rows)
    assert samples == ['=T("S1")', '=T("S2")', '=T("S3")']


def test_merge_empty_paths(tmp_path: Path) -> None:
    header, rows = merge_report_csvs([])
    assert header == [] and rows == []


def test_write_merged_roundtrip(tmp_path: Path) -> None:
    a = tmp_path / "x.csv"
    write_csv(a, [["Sample ID"], ['=T("S1")']])
    header, rows = merge_report_csvs([a])
    target = tmp_path / "merged" / "out.csv"
    write_merged_csv(header, rows, target)
    with open(target, encoding="cp1252", newline="") as f:
        content = list(csv.reader(f, delimiter=";"))
    assert content == [["Sample ID"], ['=T("S1")']]

