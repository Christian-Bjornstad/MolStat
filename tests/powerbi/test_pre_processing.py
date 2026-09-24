import csv

from tools.build_pre_sources import build, DATA
from tools.process_pre_reports import process


def raw(path, rows):
    with path.open("w", encoding="cp1252", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Sample ID", "PID", "Analyse", "Tidspunkt opprettet", "Tidspunkt analyseresultat", "Tidspunkt godkjenning"])
        writer.writerows(rows)


def test_pre_lookup_covers_user_corrected_idylla():
    summary = build()
    assert summary["lookup_codes"] == 50
    assert len(summary["classifications_from_user"]) == 5
    with (DATA / "analyse_lookup.csv").open(encoding="utf-8-sig", newline="") as handle:
        lookup = {row["Analyse"]: row for row in csv.DictReader(handle, delimiter=";")}
    assert lookup["FORBIDYLLA-E-OU"]["Aktivitetstype"] == "UtførtForbehandling"
    assert lookup["EKSTRAMAXRNA-H-OU"]["NormProsess"] == "1"
    assert lookup["MYRIAD-OU"]["NormTotalt"] == "40"


def test_pre_joins_sample_events_and_deduplicates_activity(tmp_path):
    build()
    source = tmp_path / "resultater.csv"
    raw(source, [
        ["SECRET", "PERSON", "EKSTRAKSJON-OU", "01.03.2026 08:00:00", "01.03.2026 09:00:00", ""],
        ["SECRET", "PERSON", "FORBVEVDNA-OU", "01.03.2026 08:00:00", "01.03.2026 12:00:00", ""],
        ["SECRET", "PERSON", "EKSTRAMAXDNA-OU", "01.03.2026 08:00:00", "02.03.2026 08:00:00", ""],
        ["SECRET", "PERSON", "EKSTRAMAXDNA-OU", "01.03.2026 08:00:00", "02.03.2026 10:00:00", ""],
    ])
    out = tmp_path / "out"
    summary = process(source, out)
    assert summary["unique_samples_in_input"] == 1
    assert summary["activity_rows"] == 3
    assert summary["duplicate_sample_code_rows_collapsed"] == 1
    with (out / "resultater.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["Analyse"]: row for row in csv.DictReader(handle, delimiter=";")}
    assert rows["FORBVEVDNA-OU"]["Prosessdager"] == "0.1250000000"
    assert rows["EKSTRAMAXDNA-OU"]["Prosessdager"] == "0.8333333333"
    assert rows["EKSTRAMAXDNA-OU"]["Totaldager"] == "1.0000000000"
    assert "SECRET" not in (out / "resultater.csv").read_text(encoding="utf-8-sig")
    assert "PERSON" not in (out / "resultater.csv").read_text(encoding="utf-8-sig")


def test_pre_combines_monthly_files_before_timing(tmp_path):
    build()
    source = tmp_path / "exports"
    source.mkdir()
    raw(source / "march.csv", [["S1", "P1", "FORBVEVDNA-OU", "01.03.2026 08:00:00", "31.03.2026 12:00:00", ""]])
    raw(source / "april.csv", [["S1", "P1", "EKSTRAMAXDNA-OU", "01.03.2026 08:00:00", "01.04.2026 12:00:00", ""]])
    out = tmp_path / "out"
    summary = process(source, out)
    assert summary["input_files"] == 2
    with (out / "resultater.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["Analyse"]: row for row in csv.DictReader(handle, delimiter=";")}
    assert rows["EKSTRAMAXDNA-OU"]["Prosessdager"] == "1.0000000000"
