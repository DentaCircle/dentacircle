"""Care plan names and the only status moves an item may take.

A plan is open while any item is planned or started. There is no stored plan status.
"""

from collections.abc import Sequence

MAX_LABEL_LENGTH = 200
CARE_ITEM_STATUSES = ("planned", "started", "completed", "cancelled")
# Targets of POST /care-items/{id}/status. `planned` is only the starting status.
STATUS_TARGETS = ("started", "completed", "cancelled")
OPEN_STATUSES = frozenset(("planned", "started"))
RENAMEABLE_STATUSES = OPEN_STATUSES
# From-status to the targets an item may take next. Every other pair is refused.
STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "planned": frozenset(("started", "completed", "cancelled")),
    "started": frozenset(("completed", "cancelled")),
    "completed": frozenset(),
    "cancelled": frozenset(),
}
CARE_READ_ROLES = ("clinician", "receptionist", "clinic_admin")
CARE_WRITE_ROLES = ("clinician", "clinic_admin")


class CareFieldError(Exception):
    """One field failed a rule. `code` is a validation name and carries no submitted value."""

    def __init__(self, field: str, code: str) -> None:
        self.field = field
        self.code = code
        super().__init__(code)


def clean_label(value: str, field: str) -> str:
    """Trim a title or service name. Blank and over-long values are refused."""
    trimmed = value.strip()
    if not trimmed:
        raise CareFieldError(field, "string_too_short")
    if len(trimmed) > MAX_LABEL_LENGTH:
        raise CareFieldError(field, "string_too_long")
    return trimmed


def is_open(statuses: Sequence[str]) -> bool:
    """True when at least one item is still planned or started."""
    return any(status in OPEN_STATUSES for status in statuses)


def can_move(current: str, target: str) -> bool:
    """True when `current` may become `target`. The same status again is refused."""
    return target in STATUS_TRANSITIONS.get(current, frozenset())


def can_rename(status: str) -> bool:
    """A completed or cancelled item keeps the name it had."""
    return status in RENAMEABLE_STATUSES
