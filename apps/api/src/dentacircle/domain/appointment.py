"""Appointment statuses, who may book, and which start times are free.

Slots are clinic-local wall times. A time that does not exist on a daylight-saving
change is skipped. Asia/Kolkata has no daylight-saving change.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

APPOINTMENT_STATUSES = (
    "scheduled",
    "arrived",
    "in_progress",
    "completed",
    "cancelled",
    "no_show",
)
# These do not occupy the clinician. The exclusion constraint uses the same pair.
NON_BLOCKING_STATUSES = ("cancelled", "no_show")
BLOCKING_STATUSES = tuple(
    status for status in APPOINTMENT_STATUSES if status not in NON_BLOCKING_STATUSES
)
APPOINTMENT_ROLES = ("receptionist", "clinician", "clinic_admin")
SLOT_STEP_MINUTES = 15
HORIZON_DAYS = 365
UPCOMING_LIMIT = 20
SCHEDULED = "scheduled"


class AppointmentFieldError(Exception):
    """One field failed a rule. `code` is a validation name and carries no submitted value."""

    def __init__(self, field: str, code: str) -> None:
        self.field = field
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class OpenInterval:
    """One open stretch on the day being booked. Times are clinic-local wall times."""

    opens_at: time
    closes_at: time


@dataclass(frozen=True)
class BusySpan:
    """A blocking appointment. Both ends are timezone-aware instants."""

    starts_at: datetime
    ends_at: datetime


def date_problem(day: date, zone: ZoneInfo, now: datetime) -> str | None:
    """Why this calendar day cannot be offered. None when it is inside the horizon."""
    _require_aware(now)
    today = now.astimezone(zone).date()
    if day < today:
        return "before_today"
    if day > today + timedelta(days=HORIZON_DAYS):
        return "beyond_horizon"
    return None


def free_slots(
    intervals: Sequence[OpenInterval],
    busy: Sequence[BusySpan],
    duration_minutes: int,
    day: date,
    zone: ZoneInfo,
    now: datetime,
) -> list[tuple[datetime, datetime]]:
    """Start times on `day` where the whole visit fits one interval and misses `busy`.

    The grid starts at each interval's opening time and steps 15 minutes.
    A slot must start after `now`. Empty intervals mean a closed day: no slots.
    """
    _require_aware(now)
    duration = timedelta(minutes=duration_minutes)
    slots: list[tuple[datetime, datetime]] = []
    for interval in sorted(intervals, key=lambda item: (item.opens_at, item.closes_at)):
        close_at = _local_instant(day, interval.closes_at, zone)
        if close_at is None:
            continue
        for clock in _grid_clocks(interval.opens_at, interval.closes_at):
            start = _local_instant(day, clock, zone)
            if start is None:
                continue
            end = start + duration
            if end > close_at or start <= now:
                continue
            if any(_overlaps(start, end, span) for span in busy):
                continue
            slots.append((start, end))
    return slots


def unavailable_reason(
    intervals: Sequence[OpenInterval],
    duration_minutes: int,
    day: date,
    zone: ZoneInfo,
    now: datetime,
    starts_at: datetime,
) -> str | None:
    """Why `starts_at` is not a slot `free_slots` would offer when nothing is busy.

    None means the start is bookable apart from a clinician or patient who is already taken.
    """
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        return "timezone_naive"
    _require_aware(now)
    local_day = starts_at.astimezone(zone).date()
    today = now.astimezone(zone).date()
    if local_day < today or starts_at <= now:
        return "past"
    if local_day > today + timedelta(days=HORIZON_DAYS):
        return "beyond_horizon"
    if local_day != day:
        return "outside_hours"
    offered = free_slots(intervals, [], duration_minutes, day, zone, now)
    if any(same_instant(start, starts_at) for start, _end in offered):
        return None
    if _matches_grid_clock(intervals, day, zone, starts_at):
        return "outside_hours"
    wall = starts_at.astimezone(zone).timetz().replace(tzinfo=None)
    if any(interval.opens_at <= wall < interval.closes_at for interval in intervals):
        return "not_on_grid"
    return "outside_hours"


def same_instant(left: datetime, right: datetime) -> bool:
    return left.astimezone(UTC) == right.astimezone(UTC)


def _require_aware(moment: datetime) -> None:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("now must be timezone-aware")


def _local_instant(day: date, clock: time, zone: ZoneInfo) -> datetime | None:
    """The first instant with this wall time, or None when the clock is skipped."""
    naive = datetime.combine(day, clock)
    attached = naive.replace(tzinfo=zone)
    restored = attached.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    if restored != naive:
        return None
    return attached


def _grid_clocks(opens_at: time, closes_at: time) -> list[time]:
    cursor = datetime.combine(date.min, opens_at)
    close = datetime.combine(date.min, closes_at)
    clocks: list[time] = []
    while cursor < close:
        clocks.append(cursor.time())
        cursor += timedelta(minutes=SLOT_STEP_MINUTES)
    return clocks


def _matches_grid_clock(
    intervals: Sequence[OpenInterval],
    day: date,
    zone: ZoneInfo,
    starts_at: datetime,
) -> bool:
    for interval in intervals:
        for clock in _grid_clocks(interval.opens_at, interval.closes_at):
            start = _local_instant(day, clock, zone)
            if start is not None and same_instant(start, starts_at):
                return True
    return False


def _overlaps(start: datetime, end: datetime, span: BusySpan) -> bool:
    return start < span.ends_at and end > span.starts_at
