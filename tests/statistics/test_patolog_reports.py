import csv
import json
from datetime import date, datetime
from pathlib import Path
import pytest

from molstat._statistics.patolog_reports import process
from molstat.fetching import UnifiedLvmsFetcher, _archive_has_month
from molstat.lvms.report_job import batch_filename, load_report_jobs, validate_report_job, ReportJobError
from molstat.statistics import StatisticsProcessor
from molstat.failures import RunFailure
from molstat.unit_settings import default_unit_file, load_unit_file, materialize_snapshot


PROCESS_HEADER = "Totalt antall registrerte rekvisisjoner.\nProfil;Lab;s_w_labprocess;Distinct_SampleId;Distinct_Ant. blokker;Distinct_Ant. glass\n"
PRODUCTION_HEADER = "Denne rapporten er tatt ut etter valgt tidsrom\nAntall prøver;Godkj. type;Profil;Prosess;Godkjent av;Ferdig farget;Godkj. når;Distinct_Ant glass\n"
MACRO_HEADER = "Liste med utførte makroer av bruker\nSampleID;Prioritet;Prosess;Makro når;Makro av;Gml ID\n"


def _roster(path: Path) -> Path:
    path.write_text("Brukernavn,Navn,Faggruppe\nESP,Eva Sigstad,HEMATO\nUXYSGA,Øystein Garred,GYN/URO\n", encoding="cp1252")
    return path


def test_existing_process_only_lege_config_adds_doctor_reports(tmp_path: Path) -> None:
    raw = json.loads(default_unit_file("lege").read_text(encoding="utf-8"))
    del raw["statistics"]["production"]
    del raw["statistics"]["macro"]
    legacy = tmp_path / "lege.json"
    legacy.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    upgraded = load_unit_file(legacy, "lege")

    assert set(upgraded.payload["statistics"]) == {"current", "previous", "production", "macro"}
    assert len(upgraded.unit.reports) == 4


def test_partial_month_does_not_count_as_historical_completion(tmp_path: Path) -> None:
    partial = tmp_path / "PAT-EGEN-PRODUKSJON-OU__2026-09-01__2026-09-15.csv"
    partial.write_text(PRODUCTION_HEADER, encoding="cp1252")
    assert not _archive_has_month(tmp_path, "PAT-EGEN-PRODUKSJON-OU", date(2026, 9, 1))
    complete = tmp_path / "PAT-EGEN-PRODUKSJON-OU__2026-09-01__2026-09-30.csv"
    complete.write_text(PRODUCTION_HEADER, encoding="cp1252")
    assert _archive_has_month(tmp_path, "PAT-EGEN-PRODUKSJON-OU", date(2026, 9, 1))


def test_doctor_report_requires_usernames_without_analysis_codes() -> None:
    payload = {
        "job_key": "macro", "report_type": "PRODSTAT", "category": "PATOLOGI",
        "report_id": "PAT-EGEN MAKRO", "analysis_codes": [], "usernames": ["ESP"],
        "created_from": "01.09.2026", "created_to": "30.09.2026",
        "output_stem": "PAT-EGEN-MAKRO-OU",
    }
    assert validate_report_job(payload).usernames_text() == "ESP"
    with pytest.raises(ReportJobError):
        validate_report_job({**payload, "analysis_codes": ["FLOW-01-OU"]})
    with pytest.raises(ReportJobError):
        validate_report_job({**payload, "usernames": []})


def test_lege_fetch_uses_roster_and_resumes_monthly_doctor_history(tmp_path: Path) -> None:
    definition = load_unit_file(default_unit_file("lege"))
    config_root = materialize_snapshot(tmp_path, {"lege": definition})
    calls = []

    def batch(_config, jobs_path, _keys, **kwargs):
        job = load_report_jobs(jobs_path)[0]
        calls.append(job)
        output = kwargs["repository_root"] / "rådata"
        output.mkdir(parents=True)
        if job.report_id == "PAT-EGEN PRODUKSJON":
            content = PRODUCTION_HEADER
        elif job.report_id == "PAT-EGEN MAKRO":
            content = MACRO_HEADER
        else:
            content = PROCESS_HEADER
        (output / batch_filename(job)).write_text(content, encoding="cp1252")
        return 0

    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units_path=config_root / "units.json",
        backlog_report_path=tmp_path / "unused.json", run_batch=batch,
        today=lambda: date(2026, 10, 5), history_from=date(2026, 8, 1),
        lege_lookup_path=_roster(tmp_path / "lege.csv"),
    )

    reports = fetcher.fetch_statistics(("lege",))["lege"]

    assert len(reports) == 6
    assert len(calls) == 9  # August history: three; October/September: six.
    assert {job.report_id for job in calls} == {
        "PAT-ANTALL REGISTRERTE PRØVER PROSESS-OU", "PAT-EGEN PRODUKSJON", "PAT-EGEN MAKRO"
    }
    assert all(job.usernames == ("ESP", "UXYSGA") for job in calls if job.report_id.startswith("PAT-EGEN"))
    assert all(job.interval.created_from.day == 1 for job in calls)

    calls.clear()
    fetcher.fetch_statistics(("lege",))
    assert len(calls) == 6
    assert all(job.interval.created_from.month in {9, 10} for job in calls)


def test_lege_backfill_identifies_invalid_historical_export(tmp_path: Path) -> None:
    definition = load_unit_file(default_unit_file("lege"))
    config_root = materialize_snapshot(tmp_path, {"lege": definition})

    def batch(_config, jobs_path, _keys, **kwargs):
        job = load_report_jobs(jobs_path)[0]
        output = kwargs["repository_root"] / "rådata"
        output.mkdir(parents=True)
        (output / batch_filename(job)).write_text("Invalid export\n", encoding="cp1252")
        return 0

    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units_path=config_root / "units.json",
        backlog_report_path=tmp_path / "unused.json", run_batch=batch,
        today=lambda: date(2024, 3, 5),
    )
    with pytest.raises(RunFailure, match="CSV_INVALID.*patolog/backfill/previous/2024-01"):
        fetcher.fetch_statistics(("lege",))


def test_lege_processor_identifies_invalid_doctor_export(tmp_path: Path) -> None:
    archive = tmp_path / "raw"
    archive.mkdir()
    current = archive / "PAT-PROSESS-CURRENT-OU__2026-09-01__2026-09-02.csv"
    previous = archive / "PAT-PROSESS-PREVIOUS-OU__2026-08-01__2026-08-31.csv"
    current.write_text(PROCESS_HEADER, encoding="cp1252")
    previous.write_text(PROCESS_HEADER, encoding="cp1252")
    production = archive / "PAT-EGEN-PRODUKSJON-OU__2026-09-01__2026-09-02.csv"
    production.write_text(PRODUCTION_HEADER +
                          "SAMPLE;Hovedansvarlig;HISTO;HEMATO;ESP;;INVALID;2\n", encoding="cp1252")
    macro = archive / "PAT-EGEN-MAKRO-OU__2026-09-01__2026-09-02.csv"
    macro.write_text(MACRO_HEADER, encoding="cp1252")
    processor = StatisticsProcessor(_roster(tmp_path / "lege.csv"), profile="lege")
    with pytest.raises(RunFailure, match="CSV_INVALID.*patolog/process/doctor_data"):
        processor.process("lege", [current, previous, production, production, macro, macro], tmp_path / "out")


def test_lege_processor_keeps_patient_facts_private(tmp_path: Path) -> None:
    archive = tmp_path / "raw"
    archive.mkdir()
    process_path = archive / "PAT-PROSESS-CURRENT-OU__2026-09-01__2026-09-02.csv"
    process_path.write_text(PROCESS_HEADER + '=T("HISTO");=T("OU-PAT-SPES-RA");=T("HEMATO");1;2;3\n', encoding="cp1252")
    previous = archive / "PAT-PROSESS-PREVIOUS-OU__2026-08-01__2026-08-31.csv"
    previous.write_text(PROCESS_HEADER, encoding="cp1252")
    production = archive / "PAT-EGEN-PRODUKSJON-OU__2026-09-01__2026-09-02.csv"
    production.write_text(PRODUCTION_HEADER + 'PRIVATE-1;Hovedansvarlig;HISTO;HEMATO;ESP;01.09.2026 08:00:00;02.09.2026 08:00:00;2\n', encoding="cp1252")
    macro = archive / "PAT-EGEN-MAKRO-OU__2026-09-01__2026-09-02.csv"
    macro.write_text(MACRO_HEADER + 'PRIVATE-1;Haste;HEMATO;01.09.2026 07:00:00;ESP;\n', encoding="cp1252")
    roster = _roster(tmp_path / "lege.csv")

    result = StatisticsProcessor(roster, profile="lege").process(
        "lege", [process_path, previous, production, production, macro, macro], tmp_path / "out"
    )

    assert result.publication_files == {"prosess.csv": result.antall}
    assert "PRIVATE-1" not in result.antall.read_text(encoding="utf-8-sig")
    assert result.private_files is not None
    fact = result.private_files["FactPatologRolle.csv"]
    with fact.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    assert len(rows) == 1
    assert rows[0]["SampleID"] == "PRIVATE-1"
    assert rows[0]["SvartidDager"] == "1.0"
    with result.private_files["DimPatolog.csv"].open(encoding="utf-8-sig", newline="") as stream:
        doctors = list(csv.DictReader(stream, delimiter=";"))
    assert doctors == [
        {"Brukernavn": "ESP", "Navn": "Eva Sigstad", "Faggruppe": "HEMATO"},
        {"Brukernavn": "UXYSGA", "Navn": "Øystein Garred", "Faggruppe": "GYN/URO"},
    ]
    with result.private_files["DimDato.csv"].open(encoding="utf-8-sig", newline="") as stream:
        calendar = list(csv.DictReader(stream, delimiter=";"))
    assert calendar[0]["Dato"] == "2024-01-01"
    assert any(row["Dato"] == "2026-09-24" for row in calendar)
    assert calendar[-1]["År"] == str(datetime.now().year + 1)


def test_doctor_report_processing_uses_latest_month_snapshot(tmp_path: Path) -> None:
    roster = _roster(tmp_path / "lege.csv")
    for end, sample in (("2026-09-02", "OLD"), ("2026-09-30", "NEW")):
        path = tmp_path / f"PAT-EGEN-PRODUKSJON-OU__2026-09-01__{end}.csv"
        path.write_text(PRODUCTION_HEADER + f"{sample};Hovedansvarlig;HISTO;HEMATO;ESP;01.09.2026 08:00:00;02.09.2026 08:00:00;2\n", encoding="cp1252")
    macro = tmp_path / "PAT-EGEN-MAKRO-OU__2026-09-01__2026-09-30.csv"
    macro.write_text(MACRO_HEADER, encoding="cp1252")

    paths = process(tmp_path, roster, tmp_path / "out")

    text = paths["FactPatologRolle.csv"].read_text(encoding="utf-8-sig")
    assert "NEW" in text
    assert "OLD" not in text
