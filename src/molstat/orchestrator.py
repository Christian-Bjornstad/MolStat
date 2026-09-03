from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Literal, Mapping

from .database import MolStatDatabase, WriterLeaseBusy
from .schedule import JobKind


JobStatus = Literal["succeeded", "failed", "busy"]


@dataclass(frozen=True, slots=True)
class JobResult:
    kind: JobKind
    status: JobStatus
    summary: Mapping[str, int | float | bool]
    message: str | None = None


class MolStatOrchestrator:
    def __init__(
        self,
        database: MolStatDatabase,
        runners: Mapping[JobKind, Callable[[], Mapping[str, object]]],
        *,
        owner: str,
        lease_ttl: timedelta = timedelta(minutes=30),
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        failure_reporter: Callable[[str, BaseException], None] | None = None,
    ) -> None:
        self.database = database
        self.runners = runners
        self.owner = owner
        self.lease_ttl = lease_ttl
        self._now = now
        self._failure_reporter = failure_reporter

    def run(self, kind: JobKind, trigger: str) -> JobResult:
        if kind not in self.runners:
            raise ValueError(f"Ingen kjører er konfigurert for {kind}.")
        try:
            with self.database.writer_lease(self.owner, self.lease_ttl):
                run_id = self._start_run(kind, trigger)
                try:
                    raw_summary = self.runners[kind]()
                    summary = _public_summary(raw_summary)
                    self._finish_run(run_id, "succeeded", summary)
                    return JobResult(kind, "succeeded", summary)
                except Exception as exc:
                    self._report_failure(f"{kind}_run_failed", exc)
                    self._finish_run(
                        run_id,
                        "failed",
                        {"errorType": type(exc).__name__},
                    )
                    return JobResult(
                        kind,
                        "failed",
                        {},
                        "Kjøringen feilet. Se personvernsikker diagnostikk.",
                    )
        except WriterLeaseBusy:
            return JobResult(
                kind,
                "busy",
                {},
                "En annen MolStat-kjøring er allerede aktiv.",
            )

    def _report_failure(self, stage: str, error: BaseException) -> None:
        if self._failure_reporter is None:
            return
        try:
            self._failure_reporter(stage, error)
        except Exception:
            # Diagnostics must never hide or replace the original job result.
            pass

    def _start_run(self, kind: JobKind, trigger: str) -> int:
        started_at = self._now().astimezone(timezone.utc).isoformat()
        with self.database._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO job_run(kind, trigger, status, started_at)
                VALUES (?, ?, 'running', ?)
                """,
                (kind, trigger, started_at),
            )
        return int(cursor.lastrowid)

    def _finish_run(
        self,
        run_id: int,
        status: Literal["succeeded", "failed"],
        summary: Mapping[str, object],
    ) -> None:
        finished_at = self._now().astimezone(timezone.utc).isoformat()
        with self.database._connect() as connection:
            connection.execute(
                """
                UPDATE job_run
                SET status = ?, finished_at = ?, summary = ?
                WHERE id = ?
                """,
                (
                    status,
                    finished_at,
                    json.dumps(summary, ensure_ascii=False, sort_keys=True),
                    run_id,
                ),
            )


def _public_summary(
    raw_summary: Mapping[str, object],
) -> dict[str, int | float | bool]:
    return {
        key: value
        for key, value in raw_summary.items()
        if isinstance(value, (int, float, bool))
    }
