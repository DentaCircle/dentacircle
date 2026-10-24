"""External lab work: statuses, who may touch it, and whether it is late.

Pending is requested and not back. Ready is back at the clinic. Collected means
the patient has taken it. Collected and cancelled do not move again.
`overdue` is calculated. It is never stored.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from dentacircle.domain.appointment import date_problem

MAX_TITLE_LENGTH = 200
LAB_WORK_STATUSES = ("pending", "ready", "collected", "cancelled")
# Targets of POST /lab-work/{id}/status. `pending` is only the starting status.
STATUS_TARGETS = ("ready", "collected", "cancelled")
OPEN_STATUSES = frozenset(("pending", "ready"))
LAB_WORK_VIEWS = ("open", "all")
# From-status to the targets an item may take next. Every other pair is refused.
STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset(("ready", "cancelled")),
    "ready": frozenset(("collected", "cancelled")),
    "collected": frozenset(),
    "cancelled": frozenset(),
}
STATUS_KIND = {
    "ready": "lab_work_ready",
    "collected": "lab_work_collected",
    "cancelled": "lab_work_cancelled",
}
LAB_WORK_ROLES = ("clinician", "receptionist", "clinic_admin")


class LabWorkFieldError(Exception):
    """One field failed a rule. `code` is a validation name and carries no submitted value."""

    def __init__(self, field: str, code: str) -> None:
        self.field = field
        self.code = code
        super().__init__(code)


def clean_title(value: str) -> str:
    """Trim a title. Blank and over-long values are refused. Same bounds as a care item name."""
    trimmed = value.strip()
    if not trimmed:
        raise LabWorkFieldError("title", "string_too_short")
    if len(trimmed) > MAX_TITLE_LENGTH:
        raise LabWorkFieldError("title", "string_too_long")
    return trimmed


def expected_on_problem(expected_on: date, zone: ZoneInfo, now: datetime) -> str | None:
    """Why this date is outside today through the booking horizon. None when it is allowed."""
    return date_problem(expected_on, zone, now)


def can_move(current: str, target: str) -> bool:
    """True when `current` may become `target`. The same status again is refused."""
    return target in STATUS_TRANSITIONS.get(current, frozenset())


def is_overdue(status: str, expected_on: date | None, today: date) -> bool:
    """A pending item whose expected date is before today. Ready work is never overdue."""
    return status == "pending" and expected_on is not None and expected_on < today


def statuses_for_view(view: str) -> frozenset[str]:
    """`open` is work the patient has not collected. `all` adds the final statuses."""
    if view == "open":
        return OPEN_STATUSES
    if view == "all":
        return frozenset(LAB_WORK_STATUSES)
    raise LabWorkFieldError("view", "literal_error")
