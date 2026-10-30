from datetime import datetime, timedelta, timezone

import pytest

from molstat.schedule import daily_boundary


@pytest.mark.parametrize("offset", (1, 2))
def test_daily_schedule_starts_at_seven_in_local_winter_and_summer_time(offset):
    local = timezone(timedelta(hours=offset))
    assert daily_boundary(datetime(2026, 10, 28, 6, 59, 59, tzinfo=local)) is None
    start = datetime(2026, 10, 28, 7, tzinfo=local)
    assert daily_boundary(start) == start
    assert daily_boundary(start.replace(hour=23, minute=59)) == start


def test_schedule_rejects_clock_without_timezone():
    with pytest.raises(ValueError):
        daily_boundary(datetime(2026, 10, 28, 7))


def test_daily_schedule_accepts_configured_hour_and_minute():
    now = datetime(2026, 10, 28, 8, 34, 59, tzinfo=timezone.utc)
    assert daily_boundary(now, "08:35") is None
    start = now.replace(minute=35, second=0)
    assert daily_boundary(start, "08:35") == start
    assert daily_boundary(now.replace(hour=23, minute=59), "23:59") is not None


@pytest.mark.parametrize("value", ["24:00", "07:60", "7:00", "07:00:00", "text", 700, None])
def test_daily_schedule_rejects_invalid_times(value):
    with pytest.raises(ValueError):
        daily_boundary(datetime(2026, 10, 28, 8, tzinfo=timezone.utc), value)
