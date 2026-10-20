"""Month-end clamp, leap years, and clinic-local completion dates."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from dentacircle.domain.recall import (
    add_months,
    recall_due_on,
    recall_months_problem,
    recall_timing,
)

_KOLKATA = ZoneInfo("Asia/Kolkata")


def test_a_shorter_month_uses_its_last_day() -> None:
    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert add_months(date(2026, 3, 31), 1) == date(2026, 4, 30)
    assert add_months(date(2026, 1, 15), 6) == date(2026, 7, 15)


def test_february_keeps_the_leap_day() -> None:
    assert add_months(date(2023, 8, 31), 6) == date(2024, 2, 29)
    assert add_months(date(2024, 8, 31), 6) == date(2025, 2, 28)


def test_the_due_date_uses_the_clinic_local_day_not_the_utc_day() -> None:
    completed_at = datetime(2026, 10, 20, 20, 0, tzinfo=ZoneInfo("UTC"))
    assert completed_at.astimezone(_KOLKATA).date() == date(2026, 10, 21)
    assert recall_due_on(completed_at, _KOLKATA, 6) == date(2027, 4, 21)


def test_timing_compares_the_stored_date_with_today() -> None:
    today = date(2026, 10, 20)
    assert recall_timing(date(2026, 10, 19), today) == "overdue"
    assert recall_timing(today, today) == "due_today"
    assert recall_timing(date(2026, 10, 21), today) == "upcoming"


def test_only_empty_or_one_to_sixty_months_are_allowed() -> None:
    assert recall_months_problem(None) is None
    assert recall_months_problem(1) is None
    assert recall_months_problem(60) is None
    assert recall_months_problem(0) == "recall_months_range"
    assert recall_months_problem(61) == "recall_months_range"
