"""Which visits can take a care session, and what one session may record.

A session is one save. It does not complete the visit, and it cannot be edited.
"""

from collections.abc import Sequence
from uuid import UUID

MAX_SESSION_ITEMS = 20
SESSION_VISIT_STATUSES = frozenset(("arrived", "in_progress"))
SESSION_RESULT_STATUSES = ("started", "completed")
CARE_SESSION_READ_ROLES = ("clinician", "receptionist", "clinic_admin")
CARE_SESSION_WRITE_ROLES = ("clinician", "clinic_admin")


class SessionFieldError(Exception):
    """The item list failed a shape rule. `code` carries no submitted value."""

    def __init__(self, field: str, code: str) -> None:
        self.field = field
        self.code = code
        super().__init__(code)


def clean_entries(entries: Sequence[tuple[UUID, str]]) -> list[tuple[UUID, str]]:
    """Keep 1 to 20 distinct items whose result is started or completed."""
    if len(entries) < 1:
        raise SessionFieldError("items", "too_short")
    if len(entries) > MAX_SESSION_ITEMS:
        raise SessionFieldError("items", "too_long")
    seen: set[UUID] = set()
    cleaned: list[tuple[UUID, str]] = []
    for item_id, status in entries:
        if status not in SESSION_RESULT_STATUSES:
            raise SessionFieldError("items", "enum")
        if item_id in seen:
            raise SessionFieldError("items", "duplicate")
        seen.add(item_id)
        cleaned.append((item_id, status))
    return cleaned


def visit_can_take_session(status: str) -> bool:
    """Only an arrived or in-progress visit can be recorded."""
    return status in SESSION_VISIT_STATUSES
