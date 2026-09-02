from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4


class WriterLeaseBusy(RuntimeError):
    """Raised when another MolStat writer still owns the database lease."""


SCHEMA_VERSION = 1

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS schema_info (
        version INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS writer_lease (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        owner TEXT NOT NULL,
        token TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_run (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        trigger TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        summary TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_file (
        id INTEGER PRIMARY KEY,
        job_kind TEXT NOT NULL,
        unit TEXT NOT NULL,
        report_name TEXT NOT NULL,
        path TEXT NOT NULL UNIQUE,
        sha256 TEXT NOT NULL,
        archived_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS statistics_publication (
        id INTEGER PRIMARY KEY,
        unit TEXT NOT NULL,
        published_at TEXT NOT NULL,
        output_name TEXT NOT NULL,
        row_count INTEGER NOT NULL,
        sha256 TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backlog_sample (
        sample_key TEXT NOT NULL,
        analysis_group TEXT NOT NULL,
        ordered_at TEXT NOT NULL,
        arrived_at TEXT,
        workflow_stage TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        PRIMARY KEY (sample_key, analysis_group)
    )
    """,
)


def _system_now() -> datetime:
    return datetime.now(timezone.utc)


class MolStatDatabase:
    def __init__(
        self,
        path: Path,
        *,
        now: Callable[[], datetime] = _system_now,
    ) -> None:
        self.path = path
        self._now = now

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def migrate(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for statement in _SCHEMA:
                    connection.execute(statement)
                row = connection.execute(
                    "SELECT version FROM schema_info LIMIT 1"
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO schema_info(version) VALUES (?)",
                        (SCHEMA_VERSION,),
                    )
                elif row[0] != SCHEMA_VERSION:
                    raise RuntimeError(f"Ukjent databaseskjema: {row[0]}")
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def schema_version(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT version FROM schema_info LIMIT 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("Databasen er ikke migrert.")
        return int(row[0])

    def table_names(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        return {str(row[0]) for row in rows}

    @contextmanager
    def writer_lease(self, owner: str, ttl: timedelta) -> Iterator[None]:
        if not owner.strip():
            raise ValueError("Lease-eier kan ikke være tom.")
        if ttl <= timedelta(0):
            raise ValueError("Lease-varighet må være positiv.")

        token = uuid4().hex
        acquired_at = _as_utc(self._now())
        expires_at = acquired_at + ttl
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                active = connection.execute(
                    "SELECT owner, expires_at FROM writer_lease WHERE singleton = 1"
                ).fetchone()
                if active is not None and datetime.fromisoformat(active[1]) > acquired_at:
                    raise WriterLeaseBusy(
                        f"Databasen brukes allerede av {active[0]}."
                    )
                connection.execute(
                    """
                    INSERT INTO writer_lease(singleton, owner, token, expires_at)
                    VALUES (1, ?, ?, ?)
                    ON CONFLICT(singleton) DO UPDATE SET
                        owner = excluded.owner,
                        token = excluded.token,
                        expires_at = excluded.expires_at
                    """,
                    (owner, token, expires_at.isoformat()),
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise

        try:
            yield
        finally:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        "DELETE FROM writer_lease WHERE singleton = 1 AND token = ?",
                        (token,),
                    )
                    connection.execute("COMMIT")
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise

    def current_lease_owner(self) -> str | None:
        now = _as_utc(self._now())
        with self._connect() as connection:
            row = connection.execute(
                "SELECT owner, expires_at FROM writer_lease WHERE singleton = 1"
            ).fetchone()
        if row is None or datetime.fromisoformat(row[1]) <= now:
            return None
        return str(row[0])

    def job_statuses(self) -> tuple[tuple[str, str], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT kind, status FROM job_run ORDER BY id"
            ).fetchall()
        return tuple((str(row[0]), str(row[1])) for row in rows)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Klokken må returnere et tidssonebevisst tidspunkt.")
    return value.astimezone(timezone.utc)
