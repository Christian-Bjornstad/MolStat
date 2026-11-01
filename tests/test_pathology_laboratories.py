import csv
import json
from dataclasses import replace
from datetime import date, datetime

import pytest

from molstat._statistics import patolog_flow as flow
from molstat.archive import RawArchive
from molstat.fetching import UnifiedLvmsFetcher
from molstat.failures import RunFailure
from molstat.lvms.report import ReportRequest
from molstat.lvms.report_job import batch_filename, load_report_jobs, validate_report_job
from molstat.unit_settings import load_unit_file
from unit_fixtures import default_unit_file


LABS = "OU-PAT-HIST-RA,OU-PAT-HIST-RH,OU-PAT-HIST-UL"
FIELDS = flow.DATE_FIELDS + ["Prøvenummer", "Lab", "Prosess", "Prioritet", "BeholderId",
    "BlokkId", "GlassId", "Glasstype", "Signert av", "Godkjent type"]


def definition(tmp_path):
    raw = json.loads(default_unit_file("lege").read_text("utf-8"))
    raw["statistics"]["workflow"]["laboratory"] = LABS
    path = tmp_path / "lege.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return load_unit_file(path)


def export(path, arrival, labs=LABS):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="cp1252", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS, delimiter=";")
        writer.writeheader()
        for lab in labs.split(","):
            row = dict.fromkeys(FIELDS, "")
            row.update({"Prøvenummer": f"{lab}-{arrival}", "Lab": lab, "Prosess": "HEMATO",
                        "Ankomsttid": arrival.strftime("%d.%m.%Y 08:00")})
            writer.writerow(row)


def test_three_lab_definition_validates_and_reordered_filters_share_coverage(tmp_path):
    report = definition(tmp_path).unit.report_by_key("workflow")
    assert report.laboratory == LABS
    assert report.archive_scope
    assert report.archive_scope == replace(report, laboratory=",".join(reversed(LABS.split(",")))).archive_scope
    assert report.archive_scope != replace(report, process_codes=("HUD",)).archive_scope


@pytest.mark.parametrize("laboratory", [LABS, "OU-PAT-HIST-RA"])
def test_csv_accepts_each_selected_lab_and_rejects_unselected_lab(tmp_path, laboratory):
    path = tmp_path / "source.csv"
    export(path, date(2026, 9, 1), labs=laboratory)
    rows = flow.validate_month(path, date(2026, 9, 1), date(2026, 9, 30), laboratory=laboratory)
    assert {row["Lab"] for row in rows} == set(laboratory.split(","))
    export(path, date(2026, 9, 1), labs="UNSELECTED")
    with pytest.raises(ValueError, match="laboratorium"):
        flow.validate_month(path, date(2026, 9, 1), date(2026, 9, 30), laboratory=laboratory)


@pytest.mark.parametrize("laboratory", ["OU-PAT-HIST-RA,", ",OU-PAT-HIST-RA",
    "OU-PAT-HIST-RA,,OU-PAT-HIST-RH", "OU-PAT-HIST-RA,OU-PAT-HIST-RA", "OU-PAT-HIST-RA;RH"])
def test_workflow_rejects_malformed_lab_lists(laboratory):
    raw = {"job_key": "workflow", "report_type": "PRODSTAT", "category": "PATOLOGI",
        "report_id": "PAT-TID-STØP-SNITT-OU", "analysis_codes": [], "laboratory": laboratory,
        "process_codes": ["HEMATO"], "created_from": "01.09.2026", "created_to": "30.09.2026",
        "output_stem": flow.STEM}
    with pytest.raises(ValueError):
        validate_report_job(raw)


def test_extended_filter_rebuilds_legacy_history_and_resumes_after_interruption(tmp_path):
    unit = definition(tmp_path).unit
    archive = RawArchive(tmp_path)
    legacy = tmp_path / "legacy.csv"
    export(legacy, date(2026, 8, 1), labs="OU-PAT-HIST-RA")
    archive.store(legacy, ReportRequest("statistics", "lege", flow.STEM, date(2026, 8, 1), date(2026, 10, 20)))
    calls = []
    interrupt = [True]

    def runner(config, jobs_path, keys, **kwargs):
        job, = load_report_jobs(jobs_path)
        calls.append(job)
        if interrupt[0] and job.interval.created_from.month == 9:
            raise InterruptedError("synthetic interruption")
        export(kwargs["repository_root"] / "rådata" / batch_filename(job), job.interval.created_from)
        return 0

    fetcher = UnifiedLvmsFetcher(lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units=(unit,), run_batch=runner,
        today=lambda: date(2026, 10, 21), history_from=date(2026, 8, 1))
    with pytest.raises(InterruptedError):
        fetcher.fetch_statistics(("lege",))
    assert calls[0].interval.created_from == date(2026, 8, 1)
    calls.clear()
    interrupt[0] = False
    fetched = fetcher.fetch_statistics(("lege",))["lege"]
    assert calls[0].interval.created_from == date(2026, 8, 29)
    assert [(j.interval.created_from, j.interval.created_to) for j in calls] == [
        (date(2026, 8, 29), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 30)),
        (date(2026, 10, 1), date(2026, 10, 21))]
    assert all(job.laboratory == LABS for job in calls)
    request, source = fetched[0]
    assert request.archive_scope == unit.reports[0].archive_scope
    archive.store(source, request)
    calls.clear()
    fetcher.fetch_statistics(("lege",))
    assert [(j.interval.created_from, j.interval.created_to) for j in calls] == [
        (date(2026, 10, 19), date(2026, 10, 21))]
    data = flow.read_archive(tmp_path / "data/raw/statistics/lege", as_of=datetime(2026, 10, 21, 12))
    assert len(data["Prøver"]) == 12
    assert {row["Lab"] for row in data["Prøver"]} == set(LABS.split(","))


def test_partial_manual_scope_does_not_skip_missing_historical_months(tmp_path):
    unit = definition(tmp_path).unit
    source = tmp_path / "partial.csv"
    export(source, date(2026, 10, 18))
    RawArchive(tmp_path).store(source, ReportRequest("statistics", "lege", flow.STEM,
        date(2026, 10, 18), date(2026, 10, 20), archive_scope=unit.reports[0].archive_scope))
    jobs = []

    def runner(config, jobs_path, keys, **kwargs):
        job, = load_report_jobs(jobs_path)
        jobs.append(job)
        export(kwargs["repository_root"] / "rådata" / batch_filename(job), job.interval.created_from)
        return 0

    fetcher = UnifiedLvmsFetcher(lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units=(unit,), run_batch=runner,
        today=lambda: date(2026, 10, 21), history_from=date(2026, 8, 1))
    fetcher.fetch_statistics(("lege",))
    assert jobs[0].interval.created_from == date(2026, 8, 1)


def test_large_three_lab_month_splits_into_at_most_five_day_parts(tmp_path):
    unit = definition(tmp_path).unit
    successful = []

    def runner(config, jobs_path, keys, **kwargs):
        job, = load_report_jobs(jobs_path)
        assert job.laboratory == LABS
        if (job.interval.created_to - job.interval.created_from).days >= 5:
            kwargs['error_reporter'](RunFailure('LVMS_TIMEOUT', 'synthetic_download', retryable=True))
            return 2
        successful.append(job.interval)
        export(kwargs['repository_root'] / 'rådata' / batch_filename(job), job.interval.created_from)
        return 0

    fetcher = UnifiedLvmsFetcher(lvms_config_path=tmp_path / 'lvms.json', sensitive_root=tmp_path,
        work_root=tmp_path / 'work', units=(unit,), run_batch=runner, sleep=lambda _: None,
        today=lambda: date(2026, 10, 31), history_from=date(2026, 10, 1))
    (request, source), = fetcher.fetch_statistics(('lege',))['lege']
    assert (request.date_from, request.date_to) == (date(2026, 10, 1), date(2026, 10, 31))
    assert successful[0].created_from == request.date_from
    assert successful[-1].created_to == request.date_to
    assert all((right.created_from - left.created_to).days == 1
               for left, right in zip(successful, successful[1:]))
    assert len(flow.validate_month(source, request.date_from, request.date_to, laboratory=LABS)) == 3 * len(successful)
