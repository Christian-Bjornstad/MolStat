from datetime import datetime

import pytest

from molstat.schedule import due_jobs


@pytest.mark.parametrize("hour", range(6, 19))
def test_backlog_is_due_each_inclusive_operating_hour(hour: int) -> None:
    now = datetime(2026, 9, 2, hour, 17)

    assert "backlog" in due_jobs(
        now, {"backlog": None, "statistics": datetime(2026, 9, 2, 5, 0)}
    )


@pytest.mark.parametrize("hour", (0, 5, 19, 23))
def test_backlog_is_not_due_outside_operating_hours(hour: int) -> None:
    assert "backlog" not in due_jobs(
        datetime(2026, 9, 2, hour, 0),
        {"backlog": None, "statistics": None},
    )


def test_statistics_is_due_once_during_five_oclock_hour() -> None:
    now = datetime(2026, 9, 2, 5, 42)

    assert due_jobs(now, {"statistics": None, "backlog": None}) == (
        "statistics",
    )
    assert due_jobs(
        now,
        {
            "statistics": datetime(2026, 9, 2, 5, 1),
            "backlog": None,
        },
    ) == ()


def test_backlog_is_due_only_once_per_hour() -> None:
    now = datetime(2026, 9, 2, 8, 50)

    assert due_jobs(
        now,
        {
            "statistics": datetime(2026, 9, 2, 5, 0),
            "backlog": datetime(2026, 9, 2, 8, 1),
        },
    ) == ()
