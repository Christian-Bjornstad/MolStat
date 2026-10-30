from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import math
import sqlite3
from typing import Literal, Mapping, Sequence

from .database import MolStatDatabase, WriterLeaseBusy
from .system import CapabilityRun
from .failures import MESSAGES, RunFailure, database_failure, storage_failure
from .recovery import RetryEvent, recovery_context, uncancellable_cleanup, check_cancelled
from .modules import DEFAULT_UNITS, JobKind
from .unit_settings import UnitConfigError
from .manual_import import ManualImportError
from ._writer_lease import WriterLeaseLost
from .schedule import daily_boundary, scheduled_trigger


JobStatus = Literal["succeeded", "partial", "failed", "busy"]


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """Safe unit outcome for UI and persisted history; never contains exceptions."""

    unit_key: str
    job_kind: JobKind
    status: Literal["succeeded", "failed"]
    summary: Mapping[str, int | float | bool]
    message: str | None = None
    error_code: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True, slots=True)
class JobResult:
    kind: str
    status: JobStatus
    summary: Mapping[str, int | float | bool]
    message: str | None = None
    capability_results: tuple[CapabilityResult, ...] = ()
    error_code: str | None = None


class MolStatOrchestrator:
    def __init__(
        self,
        database: MolStatDatabase,
        runners: Mapping[
            str,
            Callable[[], Mapping[str, object] | Sequence[CapabilityRun]],
        ],
        *,
        owner: str,
        daily_time: str = "07:00",
        lease_ttl: timedelta = timedelta(minutes=30),
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        failure_reporter: Callable[[str, BaseException], None] | None = None,
        retry_reporter: Callable[[RetryEvent], None] | None = None,
    ) -> None:
        self.database = database
        self.runners = runners
        self.owner = owner
        self.daily_time = daily_time
        self.lease_ttl = lease_ttl
        self._now = now
        self._failure_reporter = failure_reporter
        self._retry_reporter = retry_reporter

    def run(self, kind: str, trigger: str) -> JobResult:
        with recovery_context(observer=self._retry_reporter):
            result = self._run(kind, trigger)
            assert result is not None
            return result

    def run_daily(self, *, now: datetime | None = None) -> JobResult | None:
        boundary = daily_boundary(now if now is not None else self._now().astimezone(), self.daily_time)
        if boundary is None:
            return None
        with recovery_context(observer=self._retry_reporter):
            return self._run("all", scheduled_trigger(boundary), scheduled=True)

    def _run(self, kind: str, trigger: str, *, scheduled: bool = False) -> JobResult | None:
        if kind not in self.runners:
            raise ValueError(f"Ingen kjører er konfigurert for {kind}.")
        failed_result: JobResult | None = None
        try:
            with self.database.writer_lease(self.owner, self.lease_ttl, renew=True):
                if scheduled and self.database.has_scheduled_attempt(trigger):
                    return None
                run_id = self._start_run(kind, trigger)
                try:
                    check_cancelled()
                    raw_result = self.runners[kind]()
                    finished_at = self._now().astimezone(timezone.utc).isoformat()
                    capability_results: tuple[CapabilityResult, ...] = ()
                    if isinstance(raw_result, Mapping):
                        status: Literal["succeeded", "partial", "failed"] = (
                            "succeeded"
                        )
                        summary = _public_summary(raw_result)
                        message = None
                    else:
                        capability_results = tuple(_capability_result(run, finished_at) for run in raw_result)
                        status, summary = self._aggregate_capabilities(raw_result)
                        message = (
                            "Deler av kjøringen feilet. Se personvernsikker diagnostikk."
                            if status == "partial"
                            else (
                                "Kjøringen feilet. Se personvernsikker diagnostikk."
                                if status == "failed"
                                else None
                            )
                        )
                    stored_summary: dict[str, object] = dict(summary)
                    if capability_results:
                        stored_summary["capability_results"] = [
                            asdict(result) for result in capability_results
                        ]
                    self._finish_run(run_id, status, stored_summary, finished_at=finished_at)
                    result = JobResult(kind, status, summary, message, capability_results)
                    if status in {"failed", "partial"}:
                        failed_result = result
                    return result
                except Exception as exc:
                    self._report_failure(f"{kind}_run_failed", exc)
                    if isinstance(exc, WriterLeaseLost):
                        raise
                    try:
                        with uncancellable_cleanup():
                            self._finish_run(run_id, "failed", {"errorType": type(exc).__name__})
                    except Exception as history_error:
                        self._report_failure(f"{kind}_history_write_failed", history_error)
                    failure = storage_failure(exc, stage="job_run")
                    failed_result = JobResult(
                        kind,
                        "failed",
                        {},
                        str(failure) if failure else "Kjøringen feilet. Se personvernsikker diagnostikk.",
                        error_code=failure.code if failure else None,
                    )
                    return failed_result
        except sqlite3.Error as exc:
            self._report_failure(f"{kind}_lease_cleanup_failed" if failed_result else f"{kind}_run_failed", exc)
            if failed_result is not None:
                return failed_result
            failure = database_failure(exc)
            return JobResult(kind, "failed", {}, str(failure), error_code=failure.code)
        except WriterLeaseBusy:
            return JobResult(
                kind,
                "busy",
                {},
                "En annen MolStat-kjøring er allerede aktiv.",
            )
        except WriterLeaseLost:
            return JobResult(kind, "failed", {}, MESSAGES["DB_LEASE_LOST"], error_code="DB_LEASE_LOST")
        except (OSError, RunFailure) as exc:
            self._report_failure(f"{kind}_lease_cleanup_failed" if failed_result else f"{kind}_run_failed", exc)
            if failed_result is not None:
                return failed_result
            failure = storage_failure(exc, stage="job_run")
            return JobResult(kind, "failed", {}, str(failure) if failure else MESSAGES["FILE_ERROR"],
                             error_code=failure.code if failure else None)

    def capability_statuses(self) -> tuple[CapabilityResult, ...]:
        """Read latest outcome per capability, including completed composite runs."""
        latest: dict[tuple[str, str], CapabilityResult] = {}
        known_keys = {unit.key for unit in DEFAULT_UNITS.active()}
        with self.database.read_connection() as connection:
            rows = connection.execute(
                "SELECT summary FROM job_run WHERE finished_at IS NOT NULL "
                "AND summary IS NOT NULL AND kind != 'publish' ORDER BY id DESC"
            )
            for (raw_summary,) in rows:
                try:
                    payload = json.loads(raw_summary)
                except (TypeError, ValueError):
                    continue
                if not isinstance(payload, dict):
                    continue
                raw_results = payload.get("capability_results", ())
                if not isinstance(raw_results, list):
                    continue
                for raw in raw_results:
                    if not isinstance(raw, dict):
                        continue
                    unit, job = raw.get("unit_key"), raw.get("job_kind")
                    status, summary = raw.get("status"), raw.get("summary")
                    if (not isinstance(unit, str) or unit not in known_keys
                            or job not in ("statistics", "backlog")
                            or status not in ("succeeded", "failed")
                            or not isinstance(summary, dict)):
                        continue
                    key = (unit, job)
                    if key in latest:
                        continue
                    code = raw.get("error_code")
                    code = code if isinstance(code, str) and code in MESSAGES else None
                    message = _failure_message(code) if status == "failed" else None
                    finished_at = raw.get("finished_at")
                    try:
                        moment = datetime.fromisoformat(finished_at) if isinstance(finished_at, str) else None
                        finished_at = moment.astimezone(timezone.utc).isoformat() if moment and moment.tzinfo else None
                    except ValueError:
                        finished_at = None
                    latest[key] = CapabilityResult(
                        unit, job, status, _public_summary(summary), message, code, finished_at
                    )
        order = {unit.key: index for index, unit in enumerate(DEFAULT_UNITS)}
        return tuple(sorted(latest.values(), key=lambda result: (
            order[result.unit_key], result.job_kind == "backlog"
        )))

    def _aggregate_capabilities(
        self,
        runs: Sequence[CapabilityRun],
    ) -> tuple[
        Literal["succeeded", "partial", "failed"],
        dict[str, int | float | bool],
    ]:
        successful = tuple(run for run in runs if run.error is None)
        failed = tuple(run for run in runs if run.error is not None)
        for run in failed:
            assert run.error is not None
            self._report_failure(
                f"{run.unit_key}_{run.job_kind}_run_failed",
                run.error,
            )
        if failed and successful:
            status: Literal["succeeded", "partial", "failed"] = "partial"
        elif failed:
            status = "failed"
        else:
            status = "succeeded"
        summary: dict[str, int | float | bool] = {
            "capabilities": len(runs),
            "succeeded": len(successful),
            "failed": len(failed),
        }
        for run in successful:
            for key, value in _public_summary(run.summary).items():
                if isinstance(value, bool):
                    continue
                summary[key] = summary.get(key, 0) + value
        return status, summary

    def _report_failure(self, stage: str, error: BaseException) -> None:
        if self._failure_reporter is None:
            return
        try:
            self._failure_reporter(stage, error)
        except Exception:
            # Diagnostics must never hide or replace the original job result.
            pass

    def _start_run(self, kind: str, trigger: str) -> int:
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
        status: Literal["succeeded", "partial", "failed"],
        summary: Mapping[str, object],
        *,
        finished_at: str | None = None,
    ) -> None:
        finished_at = finished_at or self._now().astimezone(timezone.utc).isoformat()
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
        if isinstance(value, (int, float, bool)) and math.isfinite(value)
    }


def _failure_message(code: str | None) -> str:
    return MESSAGES.get(code or "", "Kjøringen feilet. Se personvernsikker diagnostikk.")


def _capability_result(run: CapabilityRun, finished_at: str | None = None) -> CapabilityResult:
    if run.error is None:
        return CapabilityResult(run.unit_key, run.job_kind, "succeeded", _public_summary(run.summary), finished_at=finished_at)
    error = run.error
    if isinstance(error, WriterLeaseLost):
        code: str | None = "DB_LEASE_LOST"
    elif isinstance(error, sqlite3.Error):
        code: str | None = database_failure(error).code
    elif isinstance(error, UnitConfigError):
        code = "CONFIG_INVALID"
    elif isinstance(error, ManualImportError):
        code = "CSV_INVALID"
    elif (failure := storage_failure(error, stage="capability_run")) is not None and failure.code in MESSAGES:
        code = failure.code
    else:
        code = None
    return CapabilityResult(run.unit_key, run.job_kind, "failed", {}, _failure_message(code), code, finished_at)
