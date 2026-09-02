from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


class ReportJobError(ValueError):
    """A local report job is incomplete or unsafe."""


REQUIRED_JOB_FIELDS = frozenset(
    {
        "job_key",
        "report_type",
        "category",
        "report_id",
        "analysis_codes",
        "created_from",
        "created_to",
        "output_stem",
    }
)
OPTIONAL_JOB_FIELDS = frozenset({"report_groups"})
CODE_PATTERN = re.compile(r"[A-Z0-9-]{1,80}")
KEY_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}")
OUTPUT_STEM_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")


@dataclass(frozen=True)
class ReportInterval:
    created_from: date
    created_to: date

    def as_lvms(self) -> tuple[str, str]:
        return (
            self.created_from.strftime("%d.%m.%Y"),
            self.created_to.strftime("%d.%m.%Y"),
        )


@dataclass(frozen=True)
class JobReview:
    job_key: str
    report_id: str
    analysis_count: int
    created_from: str
    created_to: str


@dataclass(frozen=True)
class ReportJob:
    job_key: str
    report_type: str
    category: str
    report_id: str
    analysis_codes: tuple[str, ...]
    interval: ReportInterval
    output_stem: str
    report_groups: tuple[str, ...] = ()

    def analysis_text(self) -> str:
        return ",".join(self.analysis_codes)

    def report_groups_text(self) -> str:
        return ",".join(self.report_groups)

    def review(self) -> JobReview:
        start, end = self.interval.as_lvms()
        return JobReview(
            self.job_key,
            self.report_id,
            len(self.analysis_codes),
            start,
            end,
        )


def batch_filename(job: ReportJob) -> str:
    return (
        f"{job.output_stem}__{job.interval.created_from.isoformat()}"
        f"__{job.interval.created_to.isoformat()}.csv"
    )


def select_batch_jobs(
    jobs: tuple[ReportJob, ...], job_keys: tuple[str, ...]
) -> tuple[ReportJob, ...]:
    if not 1 <= len(job_keys) <= 3 or len(set(job_keys)) != len(job_keys):
        raise ReportJobError("batch requires one to three distinct job keys")
    jobs_by_key = {job.job_key: job for job in jobs}
    if any(key not in jobs_by_key for key in job_keys):
        raise ReportJobError("batch job was not found")
    selected = tuple(jobs_by_key[key] for key in job_keys)
    filenames = tuple(batch_filename(job) for job in selected)
    if len(set(filenames)) != len(filenames):
        raise ReportJobError("batch output targets contain duplicates")
    return selected


def _text(raw: Mapping[str, object], key: str, *, maximum: int = 120) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ReportJobError("report job text is invalid")
    return value.strip()


def _date(raw: Mapping[str, object], key: str) -> date:
    value = _text(raw, key, maximum=10)
    try:
        return datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError as exc:
        raise ReportJobError("report job date is invalid") from exc


def validate_report_job(raw: Mapping[str, object]) -> ReportJob:
    if not isinstance(raw, Mapping):
        raise ReportJobError("report job fields are invalid")
    fields = set(raw)
    allowed_fields = REQUIRED_JOB_FIELDS | OPTIONAL_JOB_FIELDS
    if not REQUIRED_JOB_FIELDS <= fields or not fields <= allowed_fields:
        raise ReportJobError("report job fields are invalid")
    job_key = _text(raw, "job_key", maximum=80)
    output_stem = _text(raw, "output_stem", maximum=80)
    if not KEY_PATTERN.fullmatch(job_key) or not OUTPUT_STEM_PATTERN.fullmatch(
        output_stem
    ):
        raise ReportJobError("report job key is invalid")
    raw_codes = raw.get("analysis_codes")
    if not isinstance(raw_codes, list) or not 1 <= len(raw_codes) <= 500:
        raise ReportJobError("analysis codes are invalid")
    codes: list[str] = []
    for raw_code in raw_codes:
        if not isinstance(raw_code, str):
            raise ReportJobError("analysis code is invalid")
        code = raw_code.strip()
        if not CODE_PATTERN.fullmatch(code):
            raise ReportJobError("analysis code is invalid")
        codes.append(code)
    if len(set(codes)) != len(codes):
        raise ReportJobError("analysis codes contain duplicates")
    raw_groups = raw.get("report_groups", [])
    if not isinstance(raw_groups, list) or len(raw_groups) > 50:
        raise ReportJobError("report groups are invalid")
    groups: list[str] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, str):
            raise ReportJobError("report group is invalid")
        group = raw_group.strip()
        if not CODE_PATTERN.fullmatch(group):
            raise ReportJobError("report group is invalid")
        groups.append(group)
    if len(set(groups)) != len(groups):
        raise ReportJobError("report groups contain duplicates")
    created_from = _date(raw, "created_from")
    created_to = _date(raw, "created_to")
    if created_from > created_to:
        raise ReportJobError("report interval is invalid")
    return ReportJob(
        job_key=job_key,
        report_type=_text(raw, "report_type"),
        category=_text(raw, "category"),
        report_id=_text(raw, "report_id"),
        analysis_codes=tuple(codes),
        interval=ReportInterval(created_from, created_to),
        output_stem=output_stem,
        report_groups=tuple(groups),
    )


def load_report_jobs(path: Path) -> tuple[ReportJob, ...]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReportJobError("report jobs could not be read") from exc
    except json.JSONDecodeError as exc:
        raise ReportJobError("report jobs are invalid JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {"jobs"}:
        raise ReportJobError("report jobs must contain one jobs list")
    items = raw["jobs"]
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ReportJobError("report jobs list is invalid")
    jobs = tuple(validate_report_job(item) for item in items)
    keys = [job.job_key for job in jobs]
    if len(set(keys)) != len(keys):
        raise ReportJobError("report job keys contain duplicates")
    return jobs

