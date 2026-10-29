import csv
from dataclasses import replace
from datetime import date
from pathlib import Path
from threading import Event
import errno
import os

import pytest

from molstat.failures import RunFailure
from molstat.fetching import UnifiedLvmsFetcher, combine_report_parts
from molstat.lvms.report_job import ReportInterval, ReportJob, batch_filename, load_report_jobs


def job(start=date(2026, 10, 1), end=date(2026, 10, 4), key="ordered"):
    return ReportJob(key, "PRODSTAT", "PATOLOGI", "PAT-DIT-ANTALL-OU", ("CALR-OU",),
                     ReportInterval(start, end), key)


def fetcher(tmp_path, runner):
    return UnifiedLvmsFetcher(lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
                              work_root=tmp_path / "jobs", units=(), run_batch=runner,
                              sleep=lambda seconds: None)


def write_report(root, report, *, header=("Kode", "Verdi")):
    path = root / "rådata" / batch_filename(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="cp1252", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(header)
        writer.writerow((report.interval.created_from.isoformat(), "blå"))
    return path


def test_report_attempts_are_single_isolated_and_keep_completed_reports(tmp_path):
    calls, failed = [], False

    def runner(config, jobs_path, keys, **kwargs):
        nonlocal failed
        reports = load_report_jobs(jobs_path)
        assert len(reports) == 1
        assert kwargs["timeout_seconds"] == 300
        report = reports[0]
        calls.append((report.job_key, kwargs["repository_root"]))
        if report.job_key == "answered" and not failed:
            failed = True
            kwargs["error_reporter"](RunFailure("LVMS_TIMEOUT", "lvms_open", retryable=True))
            return 2
        write_report(kwargs["repository_root"], report)
        return 0

    paths = fetcher(tmp_path, runner)._run_jobs((job(), job(key="answered")), "hemato")

    assert [key for key, _ in calls] == ["ordered", "answered", "answered"]
    assert len({path for _, path in calls}) == 3
    assert len(paths) == 2 and all(path.is_file() for path in paths)


def test_two_report_timeouts_split_then_combine_exact_interval(tmp_path):
    intervals = []

    def runner(config, jobs_path, keys, **kwargs):
        report, = load_report_jobs(jobs_path)
        intervals.append(report.interval)
        if (report.interval.created_to - report.interval.created_from).days > 1:
            kwargs["error_reporter"](RunFailure("LVMS_TIMEOUT", "report_1_download", retryable=True))
            return 2
        write_report(kwargs["repository_root"], report)
        return 0

    report = job()
    source, = fetcher(tmp_path, runner)._run_jobs((report,), "hemato")

    assert intervals == [report.interval, report.interval,
                         ReportInterval(date(2026, 10, 1), date(2026, 10, 2)),
                         ReportInterval(date(2026, 10, 3), date(2026, 10, 4))]
    assert source.name == batch_filename(report)
    with source.open(encoding="cp1252", newline="") as stream:
        assert list(csv.reader(stream, delimiter=";")) == [
            ["Kode", "Verdi"], ["2026-10-01", "blå"], ["2026-10-03", "blå"]]


@pytest.mark.parametrize(('code', 'stage'), [
    ('LVMS_FAILED', 'lvms_open'),
    ('LVMS_FAILED', 'report_1_fill'),
    ('LVMS_TIMEOUT', 'defined_reports'),
    ('LVMS_FORM', 'report_1_fill'),
])
def test_repeated_transient_lvms_failure_waits_retries_then_splits(tmp_path, code, stage):
    events = []

    def runner(config, jobs_path, keys, **kwargs):
        report, = load_report_jobs(jobs_path)
        events.append(('request', report.interval))
        if report.interval == job().interval:
            kwargs['error_reporter'](RunFailure(code, stage, retryable=True))
            return 2
        write_report(kwargs['repository_root'], report)
        return 0

    active = fetcher(tmp_path, runner)
    active._sleep = lambda seconds: events.append(('wait', seconds))

    source, = active._run_jobs((job(),), 'hemato')

    assert events[0] == ('request', job().interval)
    retry_index = events.index(('request', job().interval), 1)
    assert sum(seconds for kind, seconds in events[1:retry_index] if kind == 'wait') == 5.0
    assert [value for kind, value in events if kind == 'request'] == [
        job().interval, job().interval,
        ReportInterval(date(2026, 10, 1), date(2026, 10, 2)),
        ReportInterval(date(2026, 10, 3), date(2026, 10, 4))]
    with source.open(encoding='cp1252', newline='') as stream:
        assert list(csv.reader(stream, delimiter=';')) == [
            ['Kode', 'Verdi'], ['2026-10-01', 'blå'], ['2026-10-03', 'blå']]


def test_one_day_timeout_stops_after_bounded_attempts(tmp_path):
    calls = []

    def runner(config, jobs_path, keys, **kwargs):
        calls.append(load_report_jobs(jobs_path)[0].interval)
        kwargs["error_reporter"](RunFailure("LVMS_TIMEOUT", "report_1_download", retryable=True))
        return 2

    with pytest.raises(RunFailure, match="LVMS_TIMEOUT"):
        fetcher(tmp_path, runner)._run_jobs((job(end=date(2026, 10, 1)),), "hemato")
    assert len(calls) == 3


def test_split_report_rejects_changed_header_without_canonical_output(tmp_path):
    def runner(config, jobs_path, keys, **kwargs):
        report, = load_report_jobs(jobs_path)
        if (report.interval.created_to - report.interval.created_from).days > 1:
            kwargs["error_reporter"](RunFailure("LVMS_TIMEOUT", "report_1_download", retryable=True))
            return 2
        write_report(kwargs["repository_root"], report,
                     header=("Kode", "Verdi") if report.interval.created_from.day == 1 else ("Kode", "Endret"))
        return 0

    with pytest.raises(RunFailure, match="CSV_INVALID"):
        fetcher(tmp_path, runner)._run_jobs((job(),), "hemato")
    assert not list((tmp_path / "jobs").glob("*/rådata/ordered__2026-10-01__2026-10-04.csv"))


@pytest.mark.parametrize("code", ["BROWSER_CLEANUP", "LVMS_LOGIN_REQUIRED", "CONFIG_INVALID",
    "LVMS_CONFIG_INVALID", "LVMS_FORM", "LVMS_FAILED", "LVMS_TIMEOUT", "CSV_INVALID",
    "DOWNLOAD_INCOMPLETE", "CANCELLED"])
def test_permanent_failure_never_retries_or_splits(tmp_path, code):
    calls = []

    def runner(config, jobs_path, keys, **kwargs):
        calls.append(1)
        kwargs["error_reporter"](RunFailure(code, "report_1_download"))
        return 2

    with pytest.raises(RunFailure, match=code):
        fetcher(tmp_path, runner)._run_jobs((job(),), "hemato")
    assert calls == [1]


def test_retryable_storage_failure_does_not_split_report_interval(tmp_path):
    calls = []

    def runner(config, jobs_path, keys, **kwargs):
        report, = load_report_jobs(jobs_path)
        calls.append(report.interval)
        kwargs['error_reporter'](RunFailure('FILE_UNAVAILABLE', 'lvms_finalize', retryable=True))
        return 2

    with pytest.raises(RunFailure, match='FILE_UNAVAILABLE'):
        fetcher(tmp_path, runner)._run_jobs((job(),), 'hemato')
    assert calls == [job().interval] * 3


def test_timeout_splitting_stops_at_report_request_budget(tmp_path):
    calls = []
    def runner(config, jobs_path, keys, **kwargs):
        calls.append(1)
        kwargs["error_reporter"](RunFailure("LVMS_TIMEOUT", "report_1_download", retryable=True))
        return 2

    with pytest.raises(RunFailure, match="LVMS_TIMEOUT"):
        fetcher(tmp_path, runner)._run_jobs((job(start=date(2024, 1, 1), end=date(2026, 10, 20)),), "hemato")
    assert len(calls) <= 24


def test_split_utf8_report_keeps_one_bom_and_preserves_duplicate_glass_rows(tmp_path):
    parts = [tmp_path / "left.csv", tmp_path / "right.csv"]
    for source in parts:
        source.write_text('Kode;Verdi\r\nØYE;"én;glass"\r\n', encoding="utf-8-sig")
    destination = tmp_path / "combined.csv"

    combine_report_parts(parts, destination)

    assert destination.read_bytes().count(b"\xef\xbb\xbf") == 1
    with destination.open(encoding="utf-8-sig", newline="") as source:
        assert list(csv.reader(source, delimiter=";")) == [
            ["Kode", "Verdi"], ["ØYE", "én;glass"], ["ØYE", "én;glass"]]


@pytest.mark.parametrize("wrong_child_date", [False, True])
def test_split_pathology_returns_one_complete_month_file(tmp_path, wrong_child_date):
    from molstat._statistics import patolog_flow as flow
    fields = flow.DATE_FIELDS + ["Prøvenummer", "Lab", "Prosess", "Prioritet", "BeholderId",
                                "BlokkId", "GlassId", "Glasstype", "Signert av", "Godkjent type"]
    report = replace(job(), job_key="workflow", report_id="PAT-TID-STØP-SNITT-OU", analysis_codes=(),
                     output_stem=flow.STEM, laboratory="OU-PAT-HIST-RA", process_codes=("HEMATO",))
    intervals = []
    def runner(config, jobs_path, keys, **kwargs):
        current, = load_report_jobs(jobs_path)
        intervals.append(current.interval)
        if (current.interval.created_to - current.interval.created_from).days > 1:
            kwargs["error_reporter"](RunFailure("LVMS_TIMEOUT", "report_1_download", retryable=True))
            return 2
        source = kwargs["repository_root"] / "rådata" / batch_filename(current)
        source.parent.mkdir()
        row = dict.fromkeys(fields, "")
        row.update({"Prøvenummer": f"SYNTHETIC-{current.interval.created_from.day}", "Lab": "OU-PAT-HIST-RA",
                    "Prosess": "HEMATO", "Ankomsttid": current.interval.created_from.strftime("%d.%m.%Y") + " 08:00"})
        if wrong_child_date and current.interval.created_from.day == 1:
            row["Ankomsttid"] = "04.10.2026 08:00"
        with source.open("w", encoding="cp1252", newline="") as output:
            writer = csv.DictWriter(output, fields, delimiter=";")
            writer.writeheader(); writer.writerow(row)
        return 0

    if wrong_child_date:
        with pytest.raises(RunFailure, match="CSV_INVALID"):
            fetcher(tmp_path, runner)._run_jobs((report,), "lege")
        assert len(intervals) == 3
        return
    source, = fetcher(tmp_path, runner)._run_jobs((report,), "lege")

    assert len(intervals) == 4
    assert source.name == "PAT-TID-STOP-SNITT-OU__2026-10-01__2026-10-04.csv"
    assert flow.latest_months(source.parent) == {date(2026, 10, 1): (source, date(2026, 10, 4))}
    assert len(flow.validate_month(source, date(2026, 10, 1), date(2026, 10, 4))) == 2


def test_stop_after_timeout_prevents_next_report_attempt(tmp_path):
    from molstat.recovery import recovery_context
    cancel = Event()
    calls = []
    def runner(config, jobs_path, keys, **kwargs):
        calls.append(1)
        kwargs["error_reporter"](RunFailure("LVMS_TIMEOUT", "report_1_download", retryable=True))
        cancel.set()
        return 2

    with recovery_context(cancel=cancel), pytest.raises(RunFailure, match="CANCELLED"):
        fetcher(tmp_path, runner)._run_jobs((job(),), "hemato")
    assert calls == [1]


@pytest.mark.parametrize("outcome", ["denied_once", "committed_reply_lost", "unknown_no_commit"])
def test_canonical_install_handles_file_failure_without_refetch(tmp_path, monkeypatch, outcome):
    calls, moves = [], []
    report = job()
    original = os.replace
    def runner(config, jobs_path, keys, **kwargs):
        calls.append(1)
        write_report(kwargs["repository_root"], report)
        return 0
    def replace_with_failure(source, destination):
        moves.append((Path(source), Path(destination)))
        if len(moves) == 1:
            if outcome == "denied_once":
                raise PermissionError(errno.EACCES, "synthetic file lock")
            if outcome == "committed_reply_lost":
                original(source, destination)
            raise OSError(errno.EIO, "synthetic ambiguous operation")
        return original(source, destination)
    monkeypatch.setattr("molstat.fetching.os.replace", replace_with_failure)

    if outcome == "unknown_no_commit":
        with pytest.raises(OSError):
            fetcher(tmp_path, runner)._run_jobs((report,), "hemato")
        assert len(moves) == 1
        assert moves[0][0].is_file()
        assert not moves[0][1].exists()
    else:
        source, = fetcher(tmp_path, runner)._run_jobs((report,), "hemato")
        assert source.is_file()
        assert len(moves) == (2 if outcome == "denied_once" else 1)
    assert calls == [1]


def test_combining_retries_local_read_without_new_report_request(tmp_path, monkeypatch):
    parts = [tmp_path / "left.csv", tmp_path / "right.csv"]
    for part in parts:
        part.write_text("Kode;Verdi\nA;blå\n", encoding="cp1252")
    original = Path.open
    denied = []
    def open_with_one_failure(path, *args, **kwargs):
        if path == parts[1] and not denied:
            denied.append(True)
            raise PermissionError(errno.EACCES, "synthetic read lock")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", open_with_one_failure)

    combine_report_parts(parts, tmp_path / "combined.csv")

    assert denied == [True]
    assert (tmp_path / "combined.csv").read_text("cp1252").count("A;blå") == 2


def test_invalid_split_retains_original_error_if_staging_cleanup_is_denied(tmp_path, monkeypatch):
    left, right = tmp_path / "left.csv", tmp_path / "right.csv"
    left.write_text("Kode;Verdi\nA;1\n", encoding="cp1252")
    right.write_text("Kode;Endret\nB;2\n", encoding="cp1252")
    original = Path.unlink
    def locked_staging(path, *args, **kwargs):
        if path.suffix == ".tmp":
            raise PermissionError(errno.EACCES, "synthetic cleanup lock")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", locked_staging)

    with pytest.raises(RunFailure, match="CSV_INVALID"):
        combine_report_parts((left, right), tmp_path / "combined.csv")
    assert left.is_file() and right.is_file()
    assert not (tmp_path / "combined.csv").exists()
