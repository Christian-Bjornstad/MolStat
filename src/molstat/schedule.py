from __future__ import annotations

from datetime import datetime
from typing import Literal, Mapping


JobKind = Literal["statistics", "backlog"]


def due_jobs(
    now: datetime,
    last_success: Mapping[JobKind, datetime | None],
    *,
    statistics_hour: int = 5,
    backlog_first_hour: int = 6,
    backlog_last_hour: int = 18,
) -> tuple[JobKind, ...]:
    due: list[JobKind] = []
    statistics_last = last_success.get("statistics")
    if now.hour == statistics_hour and (
        statistics_last is None or statistics_last.date() < now.date()
    ):
        due.append("statistics")

    backlog_last = last_success.get("backlog")
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    if backlog_first_hour <= now.hour <= backlog_last_hour and (
        backlog_last is None or backlog_last < current_hour
    ):
        due.append("backlog")
    return tuple(due)
