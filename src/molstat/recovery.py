"""Bounded retries for explicitly safe operations, with private-data-free status."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import math
import re
import time
from threading import Event
from typing import TypeVar

from .failures import RunFailure, storage_failure


STORAGE_DELAYS = (5.0, 15.0, 30.0, 60.0)
_sleep = time.sleep
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class RetryEvent:
    stage: str
    code: str
    attempt: int
    max_attempts: int
    delay_seconds: float
    detail: str = ""

    def __str__(self) -> str:
        return (f"{self.code}: Trinn: {self.stage}; nytt forsøk {self.attempt}/{self.max_attempts} "
                f"om {self.delay_seconds:g} sekunder"
                + (f"; {self.detail}" if self.detail else ""))


_observer: ContextVar[Callable[[RetryEvent], None] | None] = ContextVar("recovery_observer", default=None)
_sleeper: ContextVar[Callable[[float], None] | None] = ContextVar("recovery_sleeper", default=None)
_cancel: ContextVar[Event | None] = ContextVar("recovery_cancel", default=None)


@contextmanager
def recovery_context(*, observer: Callable[[RetryEvent], None] | None = None,
                     sleep: Callable[[float], None] | None = None,
                     cancel: Event | None = None) -> Iterator[None]:
    """Carry progress through nested jobs without replacing a parent's observer."""
    parent_observer = _observer.get()
    if observer is not None and parent_observer is not None and observer != parent_observer:
        def combined(event: RetryEvent) -> None:
            for callback in (parent_observer, observer):
                try:
                    callback(event)
                except Exception:
                    pass
        active_observer = combined
    else:
        active_observer = observer
    observer_token = _observer.set(active_observer) if active_observer is not None else None
    sleep_token = _sleeper.set(sleep) if sleep is not None else None
    cancel_token = _cancel.set(cancel) if cancel is not None else None
    try:
        yield
    finally:
        if cancel_token is not None:
            _cancel.reset(cancel_token)
        if sleep_token is not None:
            _sleeper.reset(sleep_token)
        if observer_token is not None:
            _observer.reset(observer_token)


def check_cancelled() -> None:
    cancel = _cancel.get()
    if cancel is not None and cancel.is_set():
        raise RunFailure("CANCELLED", "cancelled")


@contextmanager
def uncancellable_cleanup() -> Iterator[None]:
    """Restoring a file set must finish even after the user requests a stop."""
    token = _cancel.set(None)
    try:
        yield
    finally:
        _cancel.reset(token)


def wait_before_retry(delay: float, *, sleep: Callable[[float], None] | None = None) -> None:
    check_cancelled()
    active_sleep = sleep or _sleeper.get() or _sleep
    cancel = _cancel.get()
    if cancel is not None and active_sleep is time.sleep:
        cancel.wait(delay)
    else:
        active_sleep(delay)
    check_cancelled()


def is_transient_storage(error: BaseException) -> bool:
    # Losing writer ownership is terminal even if renewal had an I/O cause.
    from ._writer_lease import WriterLeaseLost
    if isinstance(error, WriterLeaseLost):
        return False
    failure = storage_failure(error)
    return failure is not None and failure.retryable


def emit_retry(stage: str, error: BaseException, attempt: int, max_attempts: int, delay: float) -> None:
    observer = _observer.get()
    if observer is None:
        return
    failure = storage_failure(error, stage=stage)
    if failure is None:
        return
    try:
        safe_stage = stage if re.fullmatch(r"[a-z][a-z0-9_]{0,59}", stage) else "operation"
        observer(RetryEvent(safe_stage, failure.code, attempt, max_attempts, delay, failure.detail))
    except Exception:
        # A failing log sink or UI observer cannot replace the original result.
        pass


def retry_operation(operation: Callable[[], _T], *, stage: str,
                    delays: tuple[float, ...] = STORAGE_DELAYS,
                    retry_if: Callable[[BaseException], bool] = is_transient_storage,
                    sleep: Callable[[float], None] | None = None) -> _T:
    """Retry only the operation the caller has established is safe to repeat.

    Never wrap a business import, an uncertain commit, or an entire job here.
    Each callback must clean up its own failed attempt before returning control.
    """
    if any(not math.isfinite(delay) or delay < 0 for delay in delays):
        raise ValueError("Retry delays must be finite and nonnegative.")
    for index in range(len(delays) + 1):
        check_cancelled()
        try:
            return operation()
        except Exception as error:
            if index == len(delays) or not retry_if(error):
                raise
            delay = delays[index]
            emit_retry(stage, error, index + 2, len(delays) + 1, delay)
            wait_before_retry(delay, sleep=sleep)
    raise AssertionError("Unreachable retry state")
