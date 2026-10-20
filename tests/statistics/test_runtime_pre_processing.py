import csv

from molstat._statistics.pre_reports import process
from unit_fixtures import analysis_codes as default_lookup_path


def raw(path, rows):
    with path.open("w", encoding="cp1252", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Sample ID", "PID", "Analyse", "Tidspunkt opprettet", "Tidspunkt analyseresultat", "Tidspunkt godkjenning"])
        writer.writerows(rows)




def test_pre_joins_sample_events_and_deduplicates_activity(tmp_path):
    source = tmp_path / "resultater.csv"
    raw(source, [
        ["SECRET", "PERSON", "EKSTRAKSJON-OU", "01.03.2026 08:00:00", "01.03.2026 09:00:00", ""],
        ["SECRET", "PERSON", "FORBVEVDNA-OU", "01.03.2026 08:00:00", "01.03.2026 12:00:00", ""],
        ["SECRET", "PERSON", "EKSTRAMAXDNA-OU", "01.03.2026 08:00:00", "02.03.2026 08:00:00", ""],
        ["SECRET", "PERSON", "EKSTRAMAXDNA-OU", "01.03.2026 08:00:00", "02.03.2026 10:00:00", ""],
    ])
    out = tmp_path / "out"
    summary = process(source, out, default_lookup_path("pre"))
    assert summary["unique_samples_in_input"] == 1
    assert summary["activity_rows"] == 3
    assert summary["duplicate_sample_code_rows_collapsed"] == 1
    with (out / "resultater.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["Analyse"]: row for row in csv.DictReader(handle, delimiter=";")}
    assert rows["FORBVEVDNA-OU"]["Prosessdager"] == ""
    assert rows["EKSTRAMAXDNA-OU"]["Prosessdager"] == ""
    assert rows["EKSTRAMAXDNA-OU"]["Totaldager"] == "1.0000000000"
    assert "SECRET" not in (out / "resultater.csv").read_text(encoding="utf-8-sig")
    assert "PERSON" not in (out / "resultater.csv").read_text(encoding="utf-8-sig")


def test_pre_combines_monthly_files_before_timing(tmp_path):
    source = tmp_path / "exports"
    source.mkdir()
    raw(source / "march.csv", [["S1", "P1", "FORBVEVDNA-OU", "01.03.2026 08:00:00", "31.03.2026 12:00:00", ""]])
    raw(source / "april.csv", [["S1", "P1", "EKSTRAMAXDNA-OU", "01.03.2026 08:00:00", "01.04.2026 12:00:00", ""]])
    out = tmp_path / "out"
    summary = process(source, out, default_lookup_path("pre"))
    assert summary["input_files"] == 2
    with (out / "resultater.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["Analyse"]: row for row in csv.DictReader(handle, delimiter=";")}
    assert rows["EKSTRAMAXDNA-OU"]["Prosessdager"] == ""
