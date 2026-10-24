"""Lab work rules that do not touch the database."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from dentacircle.domain.lab_work import (
    LAB_WORK_STATUSES,
    STATUS_TARGETS,
    STATUS_TRANSITIONS,
    LabWorkFieldError,
    can_move,
    clean_title,
    expected_on_problem,
    is_overdue,
    statuses_for_view,
)

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 24, 9, 0, tzinfo=_ZONE)
_TODAY = date(2026, 10, 24)


def test_the_title_is_trimmed_and_kept_inside_two_hundred_characters() -> None:
    assert clean_title("  Crown  ") == "Crown"
    assert clean_title("x" * 200) == "x" * 200
    with pytest.raises(LabWorkFieldError) as blank:
        clean_title("   ")
    assert (blank.value.field, blank.value.code) == ("title", "string_too_short")
    with pytest.raises(LabWorkFieldError) as long:
        clean_title("x" * 201)
    assert (long.value.field, long.value.code) == ("title", "string_too_long")


def test_the_expected_date_uses_the_follow_up_window() -> None:
    assert expected_on_problem(_TODAY, _ZONE, _NOW) is None
    assert expected_on_problem(date(2027, 10, 24), _ZONE, _NOW) is None
    assert expected_on_problem(date(2026, 10, 23), _ZONE, _NOW) == "before_today"
    assert expected_on_problem(date(2027, 10, 25), _ZONE, _NOW) == "beyond_horizon"


def test_only_the_written_moves_are_allowed() -> None:
    allowed = {
        ("pending", "ready"),
        ("pending", "cancelled"),
        ("ready", "collected"),
        ("ready", "cancelled"),
    }
    for current in LAB_WORK_STATUSES:
        for target in (*STATUS_TARGETS, "pending"):
            assert can_move(current, target) is ((current, target) in allowed)
    assert STATUS_TRANSITIONS["collected"] == frozenset()
    assert STATUS_TRANSITIONS["cancelled"] == frozenset()


def test_overdue_is_only_a_pending_item_before_today() -> None:
    yesterday = date(2026, 10, 23)
    assert is_overdue("pending", yesterday, _TODAY) is True
    assert is_overdue("pending", _TODAY, _TODAY) is False
    assert is_overdue("pending", None, _TODAY) is False
    assert is_overdue("ready", yesterday, _TODAY) is False
    assert is_overdue("collected", yesterday, _TODAY) is False
    assert is_overdue("cancelled", yesterday, _TODAY) is False


def test_open_hides_work_the_patient_has_finished_with() -> None:
    assert statuses_for_view("open") == frozenset(("pending", "ready"))
    assert statuses_for_view("all") == frozenset(LAB_WORK_STATUSES)
    with pytest.raises(LabWorkFieldError):
        statuses_for_view("sent")
