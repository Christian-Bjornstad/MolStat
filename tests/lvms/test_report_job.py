from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from molstat.lvms.report_job import (
    JobReview,
    ReportJobError,
    batch_filename,
    load_report_jobs,
    select_batch_jobs,
    validate_report_job,
)


class ReportJobTests(unittest.TestCase):
    def valid(self) -> dict[str, object]:
        return {
            "job_key": "synthetic_ordered",
            "report_type": "TYPE_A",
            "category": "CATEGORY_A",
            "report_id": "REPORT-A",
            "analysis_codes": ["ANALYSIS-A", "ANALYSIS-B"],
            "created_from": "01.01.2026",
            "created_to": "21.08.2026",
            "output_stem": "synthetic_ordered",
        }

    def test_normalizes_codes_and_builds_redacted_review(self) -> None:
        job = validate_report_job(self.valid())

        self.assertEqual(job.analysis_codes, ("ANALYSIS-A", "ANALYSIS-B"))
        self.assertEqual(
            job.review(),
            JobReview(
                job_key="synthetic_ordered",
                report_id="REPORT-A",
                analysis_count=2,
                created_from="01.01.2026",
                created_to="21.08.2026",
            ),
        )
        self.assertNotIn("ANALYSIS-A", str(job.review()))

    def test_output_stem_accepts_safe_uppercase_lvms_filename(self) -> None:
        job = validate_report_job(
            {**self.valid(), "output_stem": "PAT-DIT-EKSTRAKSJON-OU"}
        )

        self.assertTrue(batch_filename(job).startswith("PAT-DIT-EKSTRAKSJON-OU__"))

    def test_approved_hematology_test_jobs_are_valid_and_ordered(self) -> None:
        jobs_path = Path(__file__).resolve().parents[1] / "jobs.hematology-test.json"

        jobs = load_report_jobs(jobs_path)

        self.assertEqual([job.job_key for job in jobs], ["ordered", "answered", "extraction"])
        self.assertEqual([len(job.analysis_codes) for job in jobs], [70, 70, 25])
        self.assertEqual(
            [job.interval.as_lvms() for job in jobs],
            [("01.08.2026", "07.08.2026")] * 3,
        )

    def test_rejects_unsafe_or_ambiguous_values(self) -> None:
        invalid = (
            {"analysis_codes": ["A", "A"]},
            {"analysis_codes": ["A,,B"]},
            {"created_from": "2026-01-01"},
            {"created_from": "22.08.2026", "created_to": "21.08.2026"},
            {"output_stem": "../escape"},
            {"job_key": ""},
        )
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises(ReportJobError):
                    validate_report_job({**self.valid(), **changes})

    def test_loads_unique_jobs_from_local_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "jobs.json"
            path.write_text(json.dumps({"jobs": [self.valid()]}), encoding="utf-8")

            jobs = load_report_jobs(path)

            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].job_key, "synthetic_ordered")

    def test_select_batch_jobs_preserves_exact_three_key_order(self) -> None:
        jobs = tuple(
            validate_report_job(
                {**self.valid(), "job_key": key, "output_stem": key}
            )
            for key in ("one", "two", "three")
        )

        selected = select_batch_jobs(jobs, ("three", "one", "two"))

        self.assertEqual(
            tuple(item.job_key for item in selected), ("three", "one", "two")
        )

    def test_select_batch_jobs_rejects_invalid_or_colliding_keys(self) -> None:
        jobs = tuple(
            validate_report_job(
                {
                    **self.valid(),
                    "job_key": key,
                    "output_stem": "shared" if key != "three" else key,
                }
            )
            for key in ("one", "two", "three")
        )
        invalid_keys = (
            (),
            ("one", "one", "two"),
            ("one", "two", "missing"),
            ("one", "two", "three"),
        )
        for keys in invalid_keys:
            with self.subTest(keys=keys):
                with self.assertRaises(ReportJobError):
                    select_batch_jobs(jobs, keys)

    def test_batch_filename_is_deterministic(self) -> None:
        job = validate_report_job(
            {
                **self.valid(),
                "job_key": "one",
                "output_stem": "one",
                "created_from": "01.08.2026",
                "created_to": "07.08.2026",
            }
        )

        self.assertEqual(
            batch_filename(job), "one__2026-08-01__2026-08-07.csv"
        )


if __name__ == "__main__":
    unittest.main()

