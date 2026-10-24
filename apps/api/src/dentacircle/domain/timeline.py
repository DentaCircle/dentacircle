"""Timeline kinds. The database check constraint lists the same names.

A row stores the kind and one subject id. It never stores a name, a date or a note.
"""

TIMELINE_KINDS = (
    "patient_registered",
    "visit_booked",
    "visit_rescheduled",
    "visit_cancelled",
    "visit_arrived",
    "visit_started",
    "visit_completed",
    "visit_no_show",
    "care_item_added",
    "care_item_started",
    "care_item_completed",
    "care_item_cancelled",
    "care_session_recorded",
    "follow_up_created",
    "follow_up_updated",
    "follow_up_contacted",
    "follow_up_booked",
    "follow_up_completed",
    "follow_up_released",
    "follow_up_cancelled",
    "recall_created",
    "recall_updated",
    "recall_contacted",
    "recall_booked",
    "recall_completed",
    "recall_released",
    "recall_cancelled",
    "document_uploaded",
)

VISIT_STATUS_KIND = {
    "arrived": "visit_arrived",
    "in_progress": "visit_started",
    "completed": "visit_completed",
    "no_show": "visit_no_show",
}

CARE_ITEM_STATUS_KIND = {
    "started": "care_item_started",
    "completed": "care_item_completed",
    "cancelled": "care_item_cancelled",
}

FOLLOW_UP_MOVE_KIND = {
    "completed": "follow_up_completed",
    "contacted": "follow_up_released",
}

RECALL_MOVE_KIND = {
    "completed": "recall_completed",
    "contacted": "recall_released",
}

TIMELINE_READ_ROLES = ("clinician", "receptionist", "clinic_admin")

_SUBJECT_COLUMNS = (
    "appointment_id",
    "care_item_id",
    "care_session_id",
    "follow_up_id",
    "recall_id",
    "document_id",
)


def subject_column(kind: str) -> str | None:
    """The one subject column this kind fills. Registration fills none."""
    if kind == "patient_registered":
        return None
    if kind.startswith("visit_"):
        return "appointment_id"
    if kind.startswith("care_item_"):
        return "care_item_id"
    if kind == "care_session_recorded":
        return "care_session_id"
    if kind.startswith("follow_up_"):
        return "follow_up_id"
    if kind.startswith("recall_"):
        return "recall_id"
    if kind == "document_uploaded":
        return "document_id"
    return None


def subject_check_sql() -> str:
    """Kind and subject column agree, and at most one subject id is set."""
    clauses = [
        f"(kind = 'patient_registered' AND {_all_null()})",
        _group("visit_", "appointment_id"),
        _group("care_item_", "care_item_id"),
        f"(kind = 'care_session_recorded' AND {_only('care_session_id')})",
        _group("follow_up_", "follow_up_id"),
        _group("recall_", "recall_id"),
        f"(kind = 'document_uploaded' AND {_only('document_id')})",
    ]
    return " OR ".join(clauses)


def _group(prefix: str, column: str) -> str:
    names = ", ".join(f"'{kind}'" for kind in TIMELINE_KINDS if kind.startswith(prefix))
    return f"(kind IN ({names}) AND {_only(column)})"


def _only(column: str) -> str:
    parts = [f"{name} IS {'NOT NULL' if name == column else 'NULL'}" for name in _SUBJECT_COLUMNS]
    return " AND ".join(parts)


def _all_null() -> str:
    return " AND ".join(f"{name} IS NULL" for name in _SUBJECT_COLUMNS)
