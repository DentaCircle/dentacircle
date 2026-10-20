"""When a completed visit should leave one open recall.

The interval lives on the appointment type. Due and overdue are calculated from the
stored date and the clinic-local today. Nothing about timing is stored.
"""

import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

RECALL_STATUSES = ("scheduled", "contacted", "booked", "completed", "cancelled")
OPEN_RECALL_STATUSES = frozenset(("scheduled", "contacted", "booked"))
DUE_LIST_STATUSES = frozenset(("scheduled", "contacted"))
CONTACTABLE_STATUSES = frozenset(("scheduled",))
BOOKABLE_STATUSES = frozenset(("scheduled", "contacted"))
CANCELLABLE_STATUSES = frozenset(("scheduled", "contacted", "booked"))
MOVABLE_RECALL_STATUSES = frozenset(("scheduled", "contacted"))
RECALL_VIEWS = ("due", "all")
RECALL_TIMINGS = ("overdue", "due_today", "upcoming")
MIN_RECALL_MONTHS = 1
MAX_RECALL_MONTHS = 60
RECALL_ROLES = ("clinician", "receptionist", "clinic_admin")


def add_months(start: date, months: int) -> date:
    """The same day N months later, or the last day when that month is shorter."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day))


def recall_due_on(completed_at: datetime, zone: ZoneInfo, months: int) -> date:
    """Clinic-local calendar date of completion, plus the type's interval."""
    return add_months(completed_at.astimezone(zone).date(), months)


def recall_timing(due_on: date, today: date) -> str:
    """overdue, due_today, or upcoming from the stored date and clinic-local today."""
    if due_on < today:
        return "overdue"
    if due_on == today:
        return "due_today"
    return "upcoming"


def recall_months_problem(months: int | None) -> str | None:
    """Why this interval is not allowed. None when it is empty or from 1 to 60."""
    if months is None:
        return None
    if months < MIN_RECALL_MONTHS or months > MAX_RECALL_MONTHS:
        return "recall_months_range"
    return None
