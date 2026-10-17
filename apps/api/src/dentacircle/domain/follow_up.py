"""When a completed visit should leave one open follow-up.

Due and overdue are not decided here. The date is stored and read back as a date.
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

FOLLOW_UP_STATUSES = ("scheduled", "contacted", "booked", "completed", "cancelled")
OPEN_FOLLOW_UP_STATUSES = frozenset(("scheduled", "contacted", "booked"))
OPEN_ITEM_STATUSES = frozenset(("planned", "started"))
DEFAULT_DUE_DAYS = 7
FOLLOW_UP_READ_ROLES = ("clinician", "receptionist", "clinic_admin")


def needs_follow_up(patient_status: str, item_statuses: Sequence[str]) -> bool:
    """An active patient with a planned or started item needs one open follow-up."""
    if patient_status != "active":
        return False
    return any(status in OPEN_ITEM_STATUSES for status in item_statuses)


def due_date(completed_at: datetime, zone: ZoneInfo) -> date:
    """Clinic-local calendar date of completion, plus the default gap."""
    return completed_at.astimezone(zone).date() + timedelta(days=DEFAULT_DUE_DAYS)
