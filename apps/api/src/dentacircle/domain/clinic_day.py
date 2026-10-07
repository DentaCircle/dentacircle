"""Default clinic day, and the checks shared by the API and the seed.

Times are clinic-local wall time. They mean something only together with the clinic timezone.
"""

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_APPOINTMENT_MINUTES = 30
MIN_DURATION_MINUTES = 5
MAX_DURATION_MINUTES = 480
MAX_INTERVALS_PER_WEEKDAY = 6


class ClinicDayValidationError(Exception):
    """A clinic day that breaks a rule. `code` names the rule and carries no submitted value."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DefaultInterval:
    """One open interval. A weekday may have several. A weekday with none is closed."""

    weekday: int
    opens_at: time
    closes_at: time


@dataclass(frozen=True)
class DefaultAppointmentType:
    name: str
    duration_minutes: int


# Monday is 0. Saturday is 5. Sunday is closed.
DEFAULT_WORKING_HOURS: tuple[DefaultInterval, ...] = tuple(
    DefaultInterval(weekday, time(9, 0), time(18, 0)) for weekday in range(6)
)

DEFAULT_APPOINTMENT_TYPES: tuple[DefaultAppointmentType, ...] = (
    DefaultAppointmentType("Consultation", 30),
    DefaultAppointmentType("Scaling", 30),
    DefaultAppointmentType("Root canal visit", 60),
    DefaultAppointmentType("Crown visit", 45),
)


def validate_timezone(name: str) -> None:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError:
        raise ClinicDayValidationError("unknown_timezone") from None


def validate_duration(minutes: int) -> None:
    if minutes < MIN_DURATION_MINUTES or minutes > MAX_DURATION_MINUTES:
        raise ClinicDayValidationError("duration_range")


def validate_optional_duration(minutes: int | None) -> None:
    if minutes is not None:
        validate_duration(minutes)


def validate_working_hours(intervals: list[tuple[int, time, time]]) -> None:
    per_day: dict[int, list[tuple[time, time]]] = {}
    for weekday, opens_at, closes_at in intervals:
        if weekday < 0 or weekday > 6:
            raise ClinicDayValidationError("weekday_range")
        if opens_at >= closes_at:
            raise ClinicDayValidationError("opens_before_closes")
        per_day.setdefault(weekday, []).append((opens_at, closes_at))
    for spans in per_day.values():
        if len(spans) > MAX_INTERVALS_PER_WEEKDAY:
            raise ClinicDayValidationError("too_many_intervals")
        ordered = sorted(spans)
        previous_close: time | None = None
        for opens_at, closes_at in ordered:
            if previous_close is not None and previous_close >= opens_at:
                raise ClinicDayValidationError("interval_overlap")
            previous_close = closes_at
