import json
import pytest
from datetime import date
from pathlib import Path

from molstat.fetching import UnifiedLvmsFetcher, plan_window
from molstat.lvms.report_job import batch_filename, load_report_jobs


def test_fetcher_keeps_safe_batch_failure_and_retries_only_before_submission(tmp_path):
    from molstat.failures import RunFailure
    calls = []
    successful = FakeBatchRunner()

    def runner(*args, **kwargs):
        calls.append(kwargs["repository_root"])
        if len(calls) == 1:
            kwargs["error_reporter"](RunFailure("LVMS_TIMEOUT", "lvms_open", retryable=True))
            return 2
        return successful(*args, **kwargs)

    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units_path=_units(tmp_path / "units.json"),
        backlog_report_path=_backlog_report(tmp_path / "backlog.json"),
        run_batch=runner, sleep=lambda seconds: None,
    )
    assert fetcher.fetch_backlog()[1].is_file()
    assert len(calls) == 2
    assert calls[0] != calls[1]


def test_fetcher_does_not_resubmit_after_download_timeout(tmp_path):
    from molstat.failures import RunFailure
    calls = []
    def runner(*args, **kwargs):
        calls.append(1)
        kwargs["error_reporter"](RunFailure("DOWNLOAD_INCOMPLETE", "report_1_download"))
        return 2
    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units_path=_units(tmp_path / "units.json"),
        backlog_report_path=_backlog_report(tmp_path / "backlog.json"), run_batch=runner,
    )
    with pytest.raises(RunFailure, match="DOWNLOAD_INCOMPLETE"):
        fetcher.fetch_backlog()
    assert len(calls) == 1


class FakeBatchRunner:
    def __init__(self) -> None:
        self.jobs = []

    def __call__(
        self,
        config_path: Path,
        jobs_path: Path,
        job_keys: tuple[str, ...],
        **kwargs,
    ) -> int:
        del config_path
        jobs = load_report_jobs(jobs_path)
        self.jobs.extend(jobs)
        assert tuple(job.job_key for job in jobs) == job_keys
        output = kwargs["repository_root"] / "rådata"
        output.mkdir(parents=True, exist_ok=True)
        for job in jobs:
            (output / batch_filename(job)).write_text("synthetic", encoding="utf-8")
        return 0


def _units(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "units": {
                    "hemato": {
                        "label": "Hemato",
                        "analysis_codes": ["CALR-OU"],
                        "reports": [
                            {
                                "job_key": "ordered",
                                "fetch_report_id": "PAT-DIT-ANTALL-OU",
                                "report_id": "PAT-DIT-ANTALL-OU",
                            }
                        ],
                    },
                    "solide": {
                        "label": "Solide",
                        "profile": "solide",
                        "analysis_codes": ["KRAS-VAR-OU"],
                        "reports": [
                            {
                                "job_key": "solide-ordered",
                                "fetch_report_id": "PAT-DIT-ANTALL-OU",
                                "report_id": "PAT-DIT-ANTALL-OU",
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _backlog_report(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_type": "PRODSTAT",
                "category": "PATOLOGI",
                "report_id": "PAT-DIT RESTANSE-OU",
                "report_groups": ["OU-HEM", "OU-MOTTAKMOLPAT"],
                "analysis_codes": ["CALR-OU"],
                "output_stem": "PAT-DIT-RESTANSE-OU",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_fetcher_runs_statistics_and_backlog_through_one_runtime(
    tmp_path: Path,
) -> None:
    runner = FakeBatchRunner()
    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms-config.json",
        sensitive_root=tmp_path / "sensitive",
        work_root=tmp_path / "sensitive" / "work",
        units_path=_units(tmp_path / "units.json"),
        backlog_report_path=_backlog_report(tmp_path / "backlog-report.json"),
        run_batch=runner,
        today=lambda: date(2026, 9, 2),
    )

    statistics = fetcher.fetch_statistics()
    backlog_request, backlog_source = fetcher.fetch_backlog()

    assert len(statistics["hemato"]) == 1
    assert statistics["hemato"][0][0].date_from == date(2024, 1, 1)
    assert statistics["hemato"][0][1].is_file()
    assert backlog_request.date_from == date(2024, 1, 1)
    assert backlog_source.is_file()
    assert runner.jobs[-1].report_groups == ("OU-HEM", "OU-MOTTAKMOLPAT")


def test_fetcher_scopes_statistics_to_requested_unit(tmp_path: Path) -> None:
    runner = FakeBatchRunner()
    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms-config.json",
        sensitive_root=tmp_path / "sensitive",
        work_root=tmp_path / "sensitive" / "work",
        units_path=_units(tmp_path / "units.json"),
        backlog_report_path=_backlog_report(tmp_path / "backlog-report.json"),
        run_batch=runner,
        today=lambda: date(2026, 9, 2),
    )

    statistics = fetcher.fetch_statistics(("solide",))

    assert tuple(statistics) == ("solide",)
    assert [job.job_key for job in runner.jobs] == ["solide-ordered"]


def test_fetcher_rejects_unknown_unit_before_running_lvms(tmp_path: Path) -> None:
    runner = FakeBatchRunner()
    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms-config.json",
        sensitive_root=tmp_path / "sensitive",
        work_root=tmp_path / "sensitive" / "work",
        units_path=_units(tmp_path / "units.json"),
        backlog_report_path=_backlog_report(tmp_path / "backlog-report.json"),
        run_batch=runner,
    )

    try:
        fetcher.fetch_statistics(("ukjent",))
    except ValueError as error:
        assert "ukjent" in str(error)
    else:
        raise AssertionError("Unknown unit should be rejected")
    assert runner.jobs == []


def test_plan_window_uses_three_day_overlap_from_last_archive(tmp_path: Path) -> None:
    archive = tmp_path / "data" / "raw" / "statistics" / "hemato"
    archive.mkdir(parents=True)
    (archive / "REPORT__2026-08-01__2026-08-31.csv").write_text("x")

    assert plan_window(
        tmp_path,
        kind="statistics",
        unit="hemato",
        baseline=date(2024, 1, 1),
        today=date(2026, 9, 2),
    ) == (date(2026, 8, 29), date(2026, 9, 2))


def test_backlog_window_ignores_existing_raw_archives(tmp_path: Path) -> None:
    archive = tmp_path / "data" / "raw" / "backlog" / "hemato"
    archive.mkdir(parents=True)
    (archive / "PAT-DIT-RESTANSE-OU__2026-09-01__2026-09-09.csv").write_text("x")
    runner = FakeBatchRunner()
    fetcher = UnifiedLvmsFetcher(
        lvms_config_path=tmp_path / "lvms-config.json",
        sensitive_root=tmp_path,
        work_root=tmp_path / "work",
        units_path=_units(tmp_path / "units.json"),
        backlog_report_path=_backlog_report(tmp_path / "backlog-report.json"),
        run_batch=runner,
        today=lambda: date(2026, 9, 10),
    )

    request, _ = fetcher.fetch_backlog()

    assert (request.date_from, request.date_to) == (
        date(2024, 1, 1),
        date(2026, 9, 10),
    )


def test_statistics_window_is_planned_separately_for_each_report(tmp_path):
    from dataclasses import replace
    from molstat._statistics.units import load_units
    unit = load_units(_units(tmp_path / 'units.json'))[0]
    unit = replace(unit, reports=(unit.reports[0], replace(unit.reports[0], job_key='result', report_id='RESULT', fetch_report_id='RESULT')))
    folder = tmp_path / 'data/raw/statistics/hemato'
    folder.mkdir(parents=True)
    (folder / 'PAT-DIT-ANTALL-OU__2024-01-01__2026-10-20.csv').write_text('existing')
    runner = FakeBatchRunner()
    fetcher = UnifiedLvmsFetcher(lvms_config_path=tmp_path / 'lvms.json', sensitive_root=tmp_path,
        work_root=tmp_path / 'work', units=(unit,), run_batch=runner, today=lambda: date(2026, 10, 21))
    fetcher.fetch_statistics(('hemato',))
    assert [j.interval.created_from for j in runner.jobs] == [date(2026, 10, 18), date(2024, 1, 1)]


@pytest.mark.parametrize('key', ['hemato', 'solide', 'flow', 'fish', 'pre'])
@pytest.mark.parametrize('populated', [False, True])
def test_every_statistics_profile_only_backfills_missing_report_history(tmp_path, key, populated):
    from unit_fixtures import default_unit_file
    from molstat.unit_settings import load_unit_file
    unit = load_unit_file(default_unit_file(key)).unit
    if populated:
        folder = tmp_path / 'data/raw/statistics' / key
        folder.mkdir(parents=True)
        for report in unit.reports:
            (folder / f'{report.report_id}__2024-01-01__2026-10-20.csv').write_text('existing')
    runner = FakeBatchRunner()
    fetcher = UnifiedLvmsFetcher(lvms_config_path=tmp_path / 'lvms.json', sensitive_root=tmp_path,
        work_root=tmp_path / 'work', units=(unit,), run_batch=runner, today=lambda: date(2026, 10, 21))
    fetched = fetcher.fetch_statistics((key,))[key]
    assert len(fetched) == len(unit.reports)
    assert all(job.interval.created_from == (date(2026, 10, 18) if populated else date(2024, 1, 1))
               and job.interval.created_to == date(2026, 10, 21) for job in runner.jobs)
