import csv
from datetime import date
from pathlib import Path
import pytest

from molstat._statistics.patolog_process import process
from molstat.fetching import UnifiedLvmsFetcher, monthly_process_windows
from molstat.lvms.report_job import batch_filename, load_report_jobs
from molstat.unit_settings import default_unit_file, load_unit_file, materialize_snapshot


HEADER = "Profil;Lab;s_w_labprocess;Distinct_SampleId;Distinct_Ant. blokker;Distinct_Ant. glass\n"


def _archive(root: Path, stem: str, end: str, counts: int, revision: str = "") -> None:
    path = root / f"{stem}__2026-09-01__{end}{revision}.csv"
    path.write_text(
        "Totalt antall registrerte rekvisisjoner.\n" + HEADER
        + f'=T("HISTO");=T("OU-PAT-SPES-RA");=T("HEMATO");{counts};8;16\n'
        + '=T("CYTO");=T("OU-PAT-CYT-RA");=T("HEMATO");2;3;4\n'
        + '=T("HISTO");=T("OU-PAT-HIST-RA");=T("URO");5;6;7\n',
        encoding="cp1252",
    )


def test_process_selects_newest_month_snapshot_and_splits_hemato(tmp_path: Path) -> None:
    _archive(tmp_path, "PAT-PROSESS-CURRENT-OU", "2026-09-03", 1)
    _archive(tmp_path, "PAT-PROSESS-PREVIOUS-OU", "2026-09-30", 10)
    _archive(tmp_path, "PAT-PROSESS-PREVIOUS-OU", "2026-09-30", 11, "__r2")
    destination = tmp_path / "processed" / "prosess.csv"

    assert process(tmp_path, destination) == 3
    with destination.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    assert {(r["Prosessgruppe"], r["AntallProver"]) for r in rows} == {
        ("Hemato Flow", "11"), ("Hemato uten Flow", "2"), ("Uro", "5")
    }
    assert all(row["UttrekkTom"] == "2026-09-30" for row in rows)


def test_fetcher_uses_two_month_windows_for_patolog(tmp_path: Path) -> None:
    definition = load_unit_file(default_unit_file("lege"))
    config_root = materialize_snapshot(tmp_path, {"lege": definition})
    jobs = []

    def batch(_config, jobs_path, keys, **kwargs):
        loaded = load_report_jobs(jobs_path)
        jobs.extend(loaded)
        assert tuple(job.job_key for job in loaded) == keys
        raw = kwargs["repository_root"] / "rådata"
        raw.mkdir(parents=True)
        for job in loaded:
            (raw / batch_filename(job)).write_text(HEADER, encoding="cp1252")
        return 0

    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units_path=config_root / "units.json",
        backlog_report_path=tmp_path / "unused.json", run_batch=batch,
        today=lambda: date(2026, 1, 1),
        history_from=date(2025, 12, 1),
    )
    result = fetcher.fetch_statistics(("lege",))["lege"]
    assert [(request.date_from, request.date_to) for request, _ in result] == [
        (date(2026, 1, 1), date(2026, 1, 1)),
        (date(2025, 12, 1), date(2025, 12, 31)),
    ]
    assert {job.report_id for job in jobs} == {"PAT-ANTALL REGISTRERTE PRØVER PROSESS-OU"}
    assert all(job.analysis_codes == () for job in jobs)
    assert monthly_process_windows(date(2026, 3, 15))["previous"] == (date(2026, 2, 1), date(2026, 2, 28))


def test_first_patolog_fetch_builds_history_one_month_at_a_time(tmp_path: Path) -> None:
    definition = load_unit_file(default_unit_file("lege"))
    config_root = materialize_snapshot(tmp_path, {"lege": definition})
    calls = []

    def batch(_config, jobs_path, keys, **kwargs):
        loaded = load_report_jobs(jobs_path)
        assert len(loaded) == 1
        job = loaded[0]
        calls.append((job.interval.created_from, job.interval.created_to))
        raw = kwargs["repository_root"] / "rådata"
        raw.mkdir(parents=True)
        (raw / batch_filename(job)).write_text(HEADER, encoding="cp1252")
        return 0

    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units_path=config_root / "units.json",
        backlog_report_path=tmp_path / "unused.json", run_batch=batch,
        today=lambda: date(2024, 4, 10),
    )
    result = fetcher.fetch_statistics(("lege",))["lege"]
    assert calls == [
        (date(2024, 1, 1), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 2, 29)),
        (date(2024, 4, 1), date(2024, 4, 10)),
        (date(2024, 3, 1), date(2024, 3, 31)),
    ]
    assert len(result) == 2
    archives = tuple((tmp_path / "raw" / "statistics" / "lege").glob("*.csv"))
    assert len(archives) == 2
    assert {"2024-01-01", "2024-02-01"} == {p.name.split("__")[1] for p in archives}

    calls.clear()
    fetcher.fetch_statistics(("lege",))
    assert calls == [
        (date(2024, 4, 1), date(2024, 4, 10)),
        (date(2024, 3, 1), date(2024, 3, 31)),
    ]


def test_patolog_backfill_resumes_after_failed_month(tmp_path: Path) -> None:
    definition = load_unit_file(default_unit_file("lege"))
    config_root = materialize_snapshot(tmp_path, {"lege": definition})
    calls = []
    fail_february = True

    def batch(_config, jobs_path, _keys, **kwargs):
        job = load_report_jobs(jobs_path)[0]
        calls.append(job.interval.created_from)
        if job.interval.created_from == date(2024, 2, 1) and fail_february:
            return 2
        raw = kwargs["repository_root"] / "rådata"
        raw.mkdir(parents=True)
        (raw / batch_filename(job)).write_text(HEADER, encoding="cp1252")
        return 0

    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units_path=config_root / "units.json",
        backlog_report_path=tmp_path / "unused.json", run_batch=batch,
        today=lambda: date(2024, 4, 10), sleep=lambda _seconds: None,
    )
    with pytest.raises(Exception):
        fetcher.fetch_statistics(("lege",))
    assert calls == [date(2024, 1, 1), date(2024, 2, 1)]
    assert len(tuple((tmp_path / "raw" / "statistics" / "lege").glob("*.csv"))) == 1

    calls.clear()
    fail_february = False
    fetcher.fetch_statistics(("lege",))
    assert calls[0] == date(2024, 2, 1)
    assert date(2024, 1, 1) not in calls
