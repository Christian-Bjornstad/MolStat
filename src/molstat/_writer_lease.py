"""Renewed writer ownership and fences for database and shared-file writes."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
from threading import Event, Thread
from typing import TYPE_CHECKING

from ._sqlite_cleanup import rollback_after_failure

if TYPE_CHECKING:
    from .database import MolStatDatabase


class WriterLeaseLost(RuntimeError):
    """The current run must stop writing after losing its database lease."""
    def __init__(self, message: str, *, reason: str = "") -> None:
        super().__init__(message)
        self.reason = reason


_active_lease: ContextVar[WriterLease | None] = ContextVar("molstat_writer_lease", default=None)


def active_writer_lease(path: Path) -> WriterLease | None:
    lease = _active_lease.get()
    if lease and os.path.normcase(str(lease.database.path.resolve())) == os.path.normcase(str(path.resolve())):
        return lease
    return None


class WriterLease:
    def __init__(self, database: MolStatDatabase, token: str, ttl: timedelta) -> None:
        self.database, self.token, self.ttl = database, token, ttl
        self.stopped, self.lost = Event(), Event()
        self.loss_reason = ""
        self.renewal_deadline = self._now() + ttl
        self.thread = Thread(target=self._heartbeat, name="molstat-writer-lease", daemon=True)

    def _now(self) -> datetime:
        value = self.database._now()
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def assert_owned(self, connection: sqlite3.Connection, *, allow_expired: bool = False) -> None:
        if self.lost.is_set():
            raise WriterLeaseLost("MolStat-kjøringen har mistet databaselåsen.", reason=self.loss_reason)
        row = sqlite3.Connection.execute(connection,
            "SELECT token, expires_at FROM writer_lease WHERE singleton = 1").fetchone()
        if row is None or row[0] != self.token:
            self.loss_reason = "OWNERSHIP_CHANGED"
        elif not allow_expired and datetime.fromisoformat(row[1]) <= self._now():
            self.loss_reason = "EXPIRED"
        else:
            return
        if self.loss_reason:
            self.lost.set()
            raise WriterLeaseLost("MolStat-kjøringen har mistet databaselåsen.", reason=self.loss_reason)

    def renew_locked(self, connection: sqlite3.Connection) -> None:
        # A transaction started while ownership was valid still holds SQLite's
        # write lock. No successor can take over until that transaction commits.
        self.assert_owned(connection, allow_expired=True)
        deadline = self._now() + self.ttl
        sqlite3.Connection.execute(connection,
            "UPDATE writer_lease SET expires_at = ? WHERE singleton = 1 AND token = ?",
            (deadline.isoformat(), self.token))
        # Retry budget only; authorisation always checks the actual database row.
        self.renewal_deadline = deadline

    def renew(self) -> None:
        if self.stopped.is_set():
            return
        if self.lost.is_set():
            raise WriterLeaseLost("MolStat-kjøringen har mistet databaselåsen.", reason=self.loss_reason)
        with self.database._connect(guard_lease=False) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                # BEGIN IMMEDIATE prevents a successor from taking ownership.
                # An unchanged token can safely be renewed after a delayed wakeup.
                self.assert_owned(connection, allow_expired=True)
                self.renew_locked(connection)
                connection.execute("COMMIT")
            except BaseException:
                rollback_after_failure(connection)
                raise

    def _heartbeat(self) -> None:
        interval = min(30.0, self.ttl.total_seconds() / 3)
        while not self.stopped.wait(interval):
            try:
                self.renew()
            except sqlite3.OperationalError as exc:
                # The current import/publication may hold the write lock. Its
                # commit renews ownership under the same lock before releasing.
                if getattr(exc, "sqlite_errorcode", 0) & 0xFF in (5, 6):
                    continue
                primary = getattr(exc, "sqlite_errorcode", 0) & 0xFF
                if primary in (8, 10, 14) and self._now() < self.renewal_deadline:
                    continue
                self.loss_reason = getattr(exc, "sqlite_errorname", "RENEWAL_FAILED")
                self.lost.set()
                return
            except Exception:
                self.loss_reason = self.loss_reason or "RENEWAL_FAILED"
                self.lost.set()
                return

    def stop(self) -> None:
        self.stopped.set()
        self.thread.join(timeout=31)

    @contextmanager
    def activate(self):
        marker = _active_lease.set(self)
        self.thread.start()
        try:
            yield self
        finally:
            self.stop()
            _active_lease.reset(marker)

    @contextmanager
    def output_guard(self):
        # Commit the renewal separately: a file PermissionError must not roll
        # back the renewed expiry and turn the original error into lease loss.
        self.renew()
        with self.database._connect(guard_lease=False) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                # Renew under the same reserved write lock before touching files.
                self.renew_locked(connection)
                yield
                self.renew_locked(connection)
                connection.execute("COMMIT")
            except BaseException:
                rollback_after_failure(connection)
                raise


@contextmanager
def guarded_output():
    lease = _active_lease.get()
    if lease is None:
        yield
    else:
        with lease.output_guard():
            yield


def checkpoint_writer_lease() -> None:
    """Confirm ownership between expensive fetch stages, before starting more work."""
    lease = _active_lease.get()
    if lease is not None:
        lease.renew()
