from __future__ import annotations

from datetime import datetime, time
import re


def parse_daily_time(value: str) -> time:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise ValueError("Daglig klokkeslett må være mellom 00:00 og 23:59 (HH:mm).")
    return time.fromisoformat(value)


def daily_boundary(now: datetime, daily_time: str = "07:00") -> datetime | None:
    """Today's configured start in the PC clock's time zone, once due."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Klokken må ha tidssone.")
    clock = parse_daily_time(daily_time)
    start = now.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)
    return start if now >= start else None
