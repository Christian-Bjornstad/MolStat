from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


class ManifestError(ValueError):
    """The run manifest or incremental plan is invalid."""


DEFAULT_OVERLAP_DAYS = 3

# First-ever fetch starts here so the initial run covers all history.
DEFAULT_BACKFILL_FROM = date(2024, 1, 1)


@dataclass(frozen=True)
class RunRecord:
    """One successfully downloaded report interval."""

    unit: str
    job_key: str
    report_id: str
    created_from: date
    created_to: date
    filename: str

    def __post_init__(self) -> None:
        if self.created_from > self.created_to:
            raise ManifestError("run record interval is invalid")


UNIT_PATTERN_MIN = 1
UNIT_PATTERN_MAX = 80


def _validate_unit(unit: str) -> str:
    text = unit.strip()
    if not text or len(text) > UNIT_PATTERN_MAX:
        raise ManifestError("unit name is invalid")
    if not all(character.isalnum() or character in "-_" for character in text):
        raise ManifestError("unit name is invalid")
    return text.lower()


def resolve_statistics_root(raw: Mapping[str, object]) -> Path:
    """Read the configured statistics root from app configuration."""
    value = raw.get("statistics_root")
    if not isinstance(value, str) or not value.strip():
        raise ManifestError("statistics_root must be a non-empty string")
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        raise ManifestError("statistics_root must be an absolute path")
    return candidate.resolve()


SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit TEXT NOT NULL,
    job_key TEXT NOT NULL,
    report_id TEXT NOT NULL,
    created_from TEXT NOT NULL,
    created_to TEXT NOT NULL,
    filename TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_lookup ON runs (unit, report_id, created_to);
"""


class ManifestStore:
    """SQLite run log on the statistics share.

    One row per successful download. The next incremental interval for a
    report is planned from the highest ``created_to`` already recorded.
    """

    def __init__(self, database_path: Path) -> None:
        self._path = Path(database_path)

    @property
    def path(self) -> Path:
        return self._path

    def connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(_SCHEMA)
        row = connection.execute(
            "SELECT version FROM schema_version"
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            connection.commit()
        elif row[0] != SCHEMA_VERSION:
            raise ManifestError("manifest schema version is unsupported")
        return connection

    def last_completed_to(self, unit: str, report_id: str) -> date | None:
        """Highest interval end recorded for the report, if any."""
        unit_text = _validate_unit(unit)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MAX(created_to) FROM runs WHERE unit = ? AND report_id = ?",
                (unit_text, report_id),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        try:
            return date.fromisoformat(row[0])
        except ValueError as exc:
            raise ManifestError("manifest contains an invalid date") from exc

    def record_run(self, record: RunRecord) -> None:
        """Persist one successful download with a short transaction."""
        unit_text = _validate_unit(record.unit)
        with self.connect() as connection:
            duplicate = connection.execute(
                "SELECT 1 FROM runs WHERE unit = ? AND filename = ?",
                (unit_text, record.filename),
            ).fetchone()
            if duplicate is not None:
                raise ManifestError("run was already recorded")
            connection.execute(
                """
                INSERT INTO runs (
                    unit, job_key, report_id, created_from, created_to,
                    filename, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    unit_text,
                    record.job_key,
                    record.report_id,
                    record.created_from.isoformat(),
                    record.created_to.isoformat(),
                    record.filename,
                    _utc_now_iso(),
                ),
            )

    def has_filename(self, unit: str, filename: str) -> bool:
        unit_text = _validate_unit(unit)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM runs WHERE unit = ? AND filename = ?",
                (unit_text, filename),
            ).fetchone()
        return row is not None


@dataclass(frozen=True)
class UnitReport:
    """One tracked report within one unit."""

    unit: str
    job_key: str
    report_id: str


def plan_incremental_interval(
    report: UnitReport,
    *,
    last_completed_to: date | None,
    today: date,
    overlap_days: int = DEFAULT_OVERLAP_DAYS,
) -> tuple[date, date]:
    """Plan the next fetch interval so nothing is missed between runs.

    Without history the interval starts at DEFAULT_BACKFILL_FROM so the
    first run fetches everything from that date to today. The window
    otherwise starts ``overlap_days`` before the day after the last
    completed interval; duplicates from the overlap are removed later by
    the documented deduplication key when raw files are merged.
    """
    if overlap_days < 0:
        raise ManifestError("overlap days is invalid")
    if last_completed_to is None:
        # First ever run: fetch everything from DEFAULT_BACKFILL_FROM to
        # today in one window.
        return DEFAULT_BACKFILL_FROM, today
    start = last_completed_to + timedelta(days=1 - overlap_days)
    end = min(today, last_completed_to + timedelta(days=30))
    if start > end:
        raise ManifestError("planned interval is empty")
    if end < today:
        # A gap larger than the safety cap means the pipeline has not run
        # for a while; surface it instead of silently skipping time.
        raise ManifestError(
            f"{report.unit}/{report.report_id}: more than 30 days since "
            "the last run; split the period manually"
        )
    return start, end


def _utc_now_iso() -> str:
    import datetime as dt

    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def load_statistics_settings(path: Path) -> Path:
    """Load the statistics root from a local JSON settings file."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestError("statistics settings could not be read") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError("statistics settings are invalid JSON") from exc
    if not isinstance(raw, dict):
        raise ManifestError("statistics settings must contain an object")
    environment_override = os.environ.get("LVMS_STATISTICS_ROOT")
    if environment_override and environment_override.strip():
        return resolve_statistics_root({"statistics_root": environment_override})
    return resolve_statistics_root(raw)

