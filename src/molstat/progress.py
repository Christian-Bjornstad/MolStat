"""Transient, private-data-free run progress carried through worker contexts."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


STAGES = {
    'started': 'Starter',
    'fetching': 'Henter data',
    'processing': 'Behandler data',
    'publishing': 'Publiserer til SharePoint',
    'excel': 'Oppdaterer Excel-søk',
    'finished': 'Fullført',
    'failed': 'Feilet – se Diagnostikk',
}


@dataclass(frozen=True, slots=True)
class RunProgress:
    unit_key: str = ''
    job_kind: str = ''
    stage: str = 'started'
    detail: str = ''
    total: int = 0

    @property
    def message(self) -> str:
        label = STAGES.get(self.stage, 'Kjøring pågår')
        return f'{label} · {self.detail}' if self.detail else label


_observer: ContextVar[Callable[[RunProgress], None] | None] = ContextVar('run_progress', default=None)


@contextmanager
def progress_context(observer: Callable[[RunProgress], None]) -> Iterator[None]:
    token = _observer.set(observer)
    try:
        yield
    finally:
        _observer.reset(token)


def _emit(event: RunProgress) -> None:
    observer = _observer.get()
    if observer is not None:
        try:
            observer(event)
        except Exception:
            # Progress reporting must never change a completed import/delivery.
            pass


def plan_progress(total: int) -> None:
    _emit(RunProgress(stage='planned', total=total))


def emit_progress(unit: str, kind: str, stage: str, detail: str = '') -> None:
    _emit(RunProgress(unit, kind, stage, detail))
