"""Free start times: the grid, breaks, busy spans, now, duration and a daylight-saving day."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dentacircle.domain.appointment import (
    BusySpan,
    OpenInterval,
    free_slots,
    unavailable_reason,
)

KOLKATA = ZoneInfo("Asia/Kolkata")
LONDON = ZoneInfo("Europe/London")
MONDAY = date(2026, 10, 12)
NOW = datetime(2026, 10, 12, 8, 0, tzinfo=KOLKATA)
OPEN = [OpenInterval(time(9, 0), time(18, 0))]


def test_slots_step_fifteen_minutes_from_opening_and_stop_when_the_visit_would_pass_close() -> None:
    slots = free_slots(OPEN, [], 30, MONDAY, KOLKATA, NOW)
    starts = [start.isoformat() for start, _end in slots]
    assert starts[0] == "2026-10-12T09:00:00+05:30"
    assert "2026-10-12T09:15:00+05:30" in starts
    assert starts[-1] == "2026-10-12T17:30:00+05:30"
    assert "2026-10-12T17:45:00+05:30" not in starts
    assert slots[0][1].isoformat() == "2026-10-12T09:30:00+05:30"


def test_a_break_is_a_gap_and_a_visit_cannot_cross_it() -> None:
    intervals = [OpenInterval(time(9, 0), time(13, 0)), OpenInterval(time(14, 0), time(18, 0))]
    slots = free_slots(intervals, [], 30, MONDAY, KOLKATA, NOW)
    starts = [start.strftime("%H:%M") for start, _end in slots]
    assert "12:30" in starts
    assert "12:45" not in starts
    assert "13:00" not in starts
    assert "14:00" in starts
    assert "17:30" in starts


def test_a_closed_day_has_no_slots() -> None:
    assert free_slots([], [], 30, MONDAY, KOLKATA, NOW) == []


def test_busy_spans_block_and_back_to_back_stays_free() -> None:
    busy = [BusySpan(_at(10, 0), _at(10, 30))]
    starts = [
        start.strftime("%H:%M") for start, _end in free_slots(OPEN, busy, 30, MONDAY, KOLKATA, NOW)
    ]
    assert "09:45" not in starts
    assert "10:00" not in starts
    assert "10:15" not in starts
    assert "10:30" in starts


def test_a_slot_that_has_already_started_is_left_out() -> None:
    now = _at(9, 20)
    starts = [
        start.strftime("%H:%M") for start, _end in free_slots(OPEN, [], 30, MONDAY, KOLKATA, now)
    ]
    assert starts[0] == "09:30"


def test_the_exact_current_minute_is_not_offered() -> None:
    now = _at(9, 15)
    starts = [
        start.strftime("%H:%M") for start, _end in free_slots(OPEN, [], 30, MONDAY, KOLKATA, now)
    ]
    assert "09:15" not in starts
    assert starts[0] == "09:30"


def test_duration_changes_the_last_slot() -> None:
    short = free_slots(OPEN, [], 15, MONDAY, KOLKATA, NOW)
    long = free_slots(OPEN, [], 60, MONDAY, KOLKATA, NOW)
    assert short[-1][0].strftime("%H:%M") == "17:45"
    assert long[-1][0].strftime("%H:%M") == "17:00"
    assert long[0][1] - long[0][0] == timedelta(minutes=60)


def test_a_grid_that_does_not_start_on_the_hour() -> None:
    slots = free_slots([OpenInterval(time(9, 10), time(10, 0))], [], 20, MONDAY, KOLKATA, NOW)
    assert [start.strftime("%H:%M") for start, _end in slots] == ["09:10", "09:25", "09:40"]


def test_a_skipped_hour_on_a_london_spring_forward_is_absent() -> None:
    # 2026-03-29: Europe/London jumps from 01:00 to 02:00.
    day = date(2026, 3, 29)
    now = datetime(2026, 3, 28, 12, 0, tzinfo=LONDON)
    slots = free_slots([OpenInterval(time(0, 0), time(4, 0))], [], 15, day, LONDON, now)
    labels = [start.strftime("%H:%M") for start, _end in slots]
    assert "00:45" in labels
    assert "01:00" not in labels
    assert "01:15" not in labels
    assert "01:45" not in labels
    assert "02:00" in labels
    two = next(start for start, _end in slots if start.strftime("%H:%M") == "02:00")
    assert two.isoformat() == "2026-03-29T02:00:00+01:00"


def test_an_ambiguous_hour_is_offered_once_at_the_first_occurrence() -> None:
    # 2026-10-25: Europe/London repeats 01:00. The slot is the earlier offset.
    day = date(2026, 10, 25)
    now = datetime(2026, 10, 24, 12, 0, tzinfo=LONDON)
    slots = free_slots([OpenInterval(time(0, 30), time(2, 30))], [], 15, day, LONDON, now)
    one = [start for start, _end in slots if start.strftime("%H:%M") == "01:00"]
    assert len(one) == 1
    assert one[0].isoformat() == "2026-10-25T01:00:00+01:00"


def test_reasons_name_past_horizon_hours_and_the_grid() -> None:
    assert unavailable_reason(OPEN, 30, MONDAY, KOLKATA, NOW, _at(8, 0)) == "past"
    later = NOW + timedelta(days=400)
    assert unavailable_reason(
        OPEN, 30, later.date(), KOLKATA, NOW, _at(10, 0) + timedelta(days=400)
    ) == ("beyond_horizon")
    tomorrow = datetime(2026, 10, 13, 8, 0, tzinfo=KOLKATA)
    assert (
        unavailable_reason(OPEN, 30, date(2026, 10, 13), KOLKATA, NOW, tomorrow) == "outside_hours"
    )
    off_grid = datetime(2026, 10, 13, 10, 7, tzinfo=KOLKATA)
    assert unavailable_reason(OPEN, 30, date(2026, 10, 13), KOLKATA, NOW, off_grid) == "not_on_grid"
    too_late = datetime(2026, 10, 13, 17, 45, tzinfo=KOLKATA)
    assert (
        unavailable_reason(OPEN, 30, date(2026, 10, 13), KOLKATA, NOW, too_late) == "outside_hours"
    )
    assert unavailable_reason(
        OPEN, 30, date(2026, 10, 13), KOLKATA, NOW, datetime(2026, 10, 13, 10, 0)
    ) == ("timezone_naive")
    booked = datetime(2026, 10, 13, 10, 0, tzinfo=KOLKATA)
    assert unavailable_reason(OPEN, 30, date(2026, 10, 13), KOLKATA, NOW, booked) is None


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 10, 12, hour, minute, tzinfo=KOLKATA)
