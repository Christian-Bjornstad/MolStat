import csv
from datetime import datetime

from molstat._statistics.fish_reports import process, turnaround
from unit_fixtures import analysis_codes as default_lookup_path


def raw(path, headers, rows):
    with path.open("w", encoding="cp1252", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(headers)
        writer.writerows(rows)




def test_fish_processes_result_turnaround_and_omits_identifiers(tmp_path):
    ordered = tmp_path / "antall.csv"
    answered = tmp_path / "resultater.csv"
    raw(ordered, ["Sample ID", "Analyse", "Tidspunkt analysebestilling"], [["SECRET", "FISH-ALKBA-OU", "01.03.2026 08:00:00"]])
    raw(answered, ["Sample ID", "PID", "Analyse", "Tidspunkt analysebestilling", "Tidspunkt analyseresultat", "Tidspunkt godkjenning"], [["SECRET", "PATIENT", "FISH-ALKBA-OU", "01.03.2026 08:00:00", "06.03.2026 08:00:00", "07.03.2026 08:00:00"]])
    out = tmp_path / "out"
    summary = process(ordered, answered, out, default_lookup_path("fish"))
    assert summary["gyldige_svartider"] == 1
    assert summary["innen_norm"] == 0
    text = (out / "resultater.csv").read_text(encoding="utf-8-sig")
    assert "SECRET" not in text and "PATIENT" not in text
    with (out / "resultater.csv").open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle, delimiter=";"))
    assert row["Svartid dager"] == "5.0000000000"
    assert row["Normstatus"] == "Ikke beregnet"


def test_fish_norm_boundary_and_bad_time():
    start = datetime(2026, 1, 1)
    assert turnaround(start, datetime(2026, 1, 6))[2] == "Ikke beregnet"
    assert turnaround(start, datetime(2026, 1, 7))[2] == "Ikke beregnet"
    assert turnaround(start, None)[1] == "Mangler tidspunkt"
