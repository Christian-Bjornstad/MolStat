from __future__ import annotations

import csv
import pytest
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


def test_merge_handles_ragged_lvms_row_without_index_error(tmp_path: Path) -> None:
    source = tmp_path / "fish.csv"
    write_csv(source, [["Sample ID", "Analyse", "Tidspunkt godkjenning"],
                       ['=T("S1")', '=T("FISH-ALKBA-OU")']])

    header, rows = merge_report_csvs([source])

    assert header == ["Sample ID", "Analyse", "Tidspunkt godkjenning"]
    assert rows == [{"Sample ID": '=T("S1")', "Analyse": '=T("FISH-ALKBA-OU")',
                     "Tidspunkt godkjenning": ""}]


def test_merge_preserves_multiline_comment_with_unescaped_inner_quotes(tmp_path):
    source = tmp_path / "fish.csv"
    source.write_text(
        'Sample ID;Analyse;Ekstern analysekommentar;PID;Materiale;Tidspunkt analysebestilling;Tidspunkt analyseresultat\n'
        '=T("S1");=T("FISH-ALKBA-OU");"Funn med "signal" i teksten\n'
        'fortsettelse; med semikolon";=T("PRIVATE");PAK;01.10.2026 08:00;03.10.2026 08:00\n'
        '=T("S2");=T("FISH-ALKBA-OU");"Vanlig ""sitert"" tekst";;BM;02.10.2026 08:00;04.10.2026 08:00\n',
        encoding="cp1252",
        newline="",
    )

    header, rows = merge_report_csvs([source])

    assert len(rows) == 2
    assert rows[0]["Ekstern analysekommentar"] == 'Funn med "signal" i teksten\nfortsettelse; med semikolon'
    assert rows[0]["PID"] == '=T("PRIVATE")'
    assert rows[0]["Tidspunkt analyseresultat"] == "03.10.2026 08:00"
    assert rows[1]["Ekstern analysekommentar"] == 'Vanlig "sitert" tekst'
    target = tmp_path / "merged.csv"
    write_merged_csv(header, rows, target)
    assert merge_report_csvs([target]) == (header, rows)


@pytest.mark.parametrize("record", [
    'S1;FISH-ALKBA-OU;"PRIVATE unfinished\n',
    'S1;FISH-ALKBA-OU;"PRIVATE comment";unexpected\n',
    'S1;FISH-ALKBA-OU\n',
])
def test_invalid_comment_record_is_rejected_without_exposing_source(tmp_path, record):
    source = tmp_path / "fish.csv"
    source.write_text('Sample ID;Analyse;Ekstern analysekommentar\n' + record,
                      encoding="cp1252", newline="")
    with pytest.raises(ValueError) as error:
        merge_report_csvs([source])
    assert "PRIVATE" not in str(error.value) and "S1" not in str(error.value)

