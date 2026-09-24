import csv
from pathlib import Path

from tools.build_flow_sources import build
from tools.process_flow_reports import process, read_lookup, turnaround


def raw(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="cp1252", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(headers)
        writer.writerows(rows)


def test_flow_lookup_preserves_code_price_conflicts():
    build()
    lookup = read_lookup()
    assert len(lookup) == 66
    assert lookup["FLOW-02-OU"]["Pris2026NOK"] == "323.60"
    assert lookup["FLOW-61-OU"]["Pris2026NOK"] == "250.00"
    assert lookup["FLOW-06-B-OU"]["Pris2026NOK"] == ""
    assert "FLOW-06-ALT-OU" not in lookup
    assert lookup["FLOW-36-OU"]["Pris2026NOK"] == ""


def test_flow_processes_two_approval_turnarounds_without_extraction(tmp_path):
    ordered = tmp_path / "PAT-DIT-ANTALL-OU.csv"
    answered = tmp_path / "PAT-DIT-RESULTATER-OU.csv"
    raw(ordered, ["Sample ID", "Analyse", "Tidspunkt analysebestilling"], [
        ["SENSITIVE1", "FLOW-02-OU", "02.09.2026 08:00:00"],
        ["SENSITIVE2", "OTHER-OU", "02.09.2026 08:00:00"],
    ])
    raw(answered, ["Sample ID", "PID", "Materiale", "Analyse", "Tidspunkt prøvetaking", "Tidspunkt opprettet", "Tidspunkt analysebestilling", "Tidspunkt analyseresultat", "Tidspunkt godkjenning"], [
        ["SENSITIVE1", "PID1", "Blod", "FLOW-02-OU", "01.09.2026 08:00:00", "02.09.2026 08:00:00", "02.09.2026 09:00:00", "02.09.2026 10:00:00", "03.09.2026 08:00:00"],
        ["SENSITIVE2", "PID2", "Blod", "FLOW-06-B-OU", "02.09.2026 08:00:00", "02.09.2026 09:00:00", "02.09.2026 10:00:00", "02.09.2026 11:00:00", "01.09.2026 08:00:00"],
    ])
    out = tmp_path / "out"
    summary = process(ordered, answered, out)
    assert summary["antall"] == 1
    assert summary["resultater"] == 2
    assert summary["valid_patient_turnaround"] == 1
    with (out / "resultater.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    assert rows[0]["Svartid prøvetaking-godkjenning dager"] == "2.0000000000"
    assert rows[0]["Svartid opprettet-godkjenning dager"] == "1.0000000000"
    assert rows[1]["Svartid prøvetaking status"] == "Negativ tid"
    assert rows[1]["Pris2026NOK"] == ""
    assert "Sample ID" not in rows[0] and "PID" not in rows[0]
    assert "SENSITIVE1" not in (out / "resultater.csv").read_text(encoding="utf-8-sig")


def test_invalid_or_missing_times_are_not_zero():
    assert turnaround(None, None) == ("", "Mangler tidspunkt")
