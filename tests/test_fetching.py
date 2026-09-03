import json
from datetime import date
from pathlib import Path

from molstat.fetching import UnifiedLvmsFetcher, plan_window
from molstat.lvms.report_job import batch_filename, load_report_jobs


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
    assert backlog_request.date_from == date(2026, 1, 1)
    assert backlog_source.is_file()
    assert runner.jobs[-1].report_groups == ("OU-HEM", "OU-MOTTAKMOLPAT")


def test_plan_window_uses_three_day_overlap_from_last_archive(tmp_path: Path) -> None:
    archive = tmp_path / "raw" / "statistics" / "hemato"
    archive.mkdir(parents=True)
    (archive / "REPORT__2026-08-01__2026-08-31.csv").write_text("x")

    assert plan_window(
        tmp_path,
        kind="statistics",
        unit="hemato",
        baseline=date(2024, 1, 1),
        today=date(2026, 9, 2),
    ) == (date(2026, 8, 29), date(2026, 9, 2))
