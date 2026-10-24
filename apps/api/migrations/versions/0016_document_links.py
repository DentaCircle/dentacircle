"""Document links and the document_uploaded timeline kind.

Revision ID: 0016_document_links
Revises: 0015_documents
Create Date: 2026-10-23

Adds nullable appointment and follow-up links on document, and document_id on
timeline_event. Drops and recreates the timeline kind and subject checks so
document_uploaded is allowed with that one subject. Existing rows stay valid:
their new columns are null.

Downgrade deletes document_uploaded timeline rows first, then restores the
previous checks and drops the new columns. Those timeline rows are not restored.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_document_links"
down_revision: str | None = "0015_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS_BEFORE = (
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
)

_SUBJECT_BEFORE = (
    "(kind = 'patient_registered' AND appointment_id IS NULL AND care_item_id IS NULL"
    " AND care_session_id IS NULL AND follow_up_id IS NULL AND recall_id IS NULL)"
    " OR (kind IN ('visit_booked', 'visit_rescheduled', 'visit_cancelled', 'visit_arrived',"
    " 'visit_started', 'visit_completed', 'visit_no_show') AND appointment_id IS NOT NULL"
    " AND care_item_id IS NULL AND care_session_id IS NULL AND follow_up_id IS NULL"
    " AND recall_id IS NULL)"
    " OR (kind IN ('care_item_added', 'care_item_started', 'care_item_completed',"
    " 'care_item_cancelled') AND appointment_id IS NULL AND care_item_id IS NOT NULL"
    " AND care_session_id IS NULL AND follow_up_id IS NULL AND recall_id IS NULL)"
    " OR (kind = 'care_session_recorded' AND appointment_id IS NULL AND care_item_id IS NULL"
    " AND care_session_id IS NOT NULL AND follow_up_id IS NULL AND recall_id IS NULL)"
    " OR (kind IN ('follow_up_created', 'follow_up_updated', 'follow_up_contacted',"
    " 'follow_up_booked', 'follow_up_completed', 'follow_up_released', 'follow_up_cancelled')"
    " AND appointment_id IS NULL AND care_item_id IS NULL AND care_session_id IS NULL"
    " AND follow_up_id IS NOT NULL AND recall_id IS NULL)"
    " OR (kind IN ('recall_created', 'recall_updated', 'recall_contacted', 'recall_booked',"
    " 'recall_completed', 'recall_released', 'recall_cancelled') AND appointment_id IS NULL"
    " AND care_item_id IS NULL AND care_session_id IS NULL AND follow_up_id IS NULL"
    " AND recall_id IS NOT NULL)"
)

_KINDS = _KINDS_BEFORE + ("document_uploaded",)

_SUBJECT = (
    "(kind = 'patient_registered' AND appointment_id IS NULL AND care_item_id IS NULL"
    " AND care_session_id IS NULL AND follow_up_id IS NULL AND recall_id IS NULL"
    " AND document_id IS NULL)"
    " OR (kind IN ('visit_booked', 'visit_rescheduled', 'visit_cancelled', 'visit_arrived',"
    " 'visit_started', 'visit_completed', 'visit_no_show') AND appointment_id IS NOT NULL"
    " AND care_item_id IS NULL AND care_session_id IS NULL AND follow_up_id IS NULL"
    " AND recall_id IS NULL AND document_id IS NULL)"
    " OR (kind IN ('care_item_added', 'care_item_started', 'care_item_completed',"
    " 'care_item_cancelled') AND appointment_id IS NULL AND care_item_id IS NOT NULL"
    " AND care_session_id IS NULL AND follow_up_id IS NULL AND recall_id IS NULL"
    " AND document_id IS NULL)"
    " OR (kind = 'care_session_recorded' AND appointment_id IS NULL AND care_item_id IS NULL"
    " AND care_session_id IS NOT NULL AND follow_up_id IS NULL AND recall_id IS NULL"
    " AND document_id IS NULL)"
    " OR (kind IN ('follow_up_created', 'follow_up_updated', 'follow_up_contacted',"
    " 'follow_up_booked', 'follow_up_completed', 'follow_up_released', 'follow_up_cancelled')"
    " AND appointment_id IS NULL AND care_item_id IS NULL AND care_session_id IS NULL"
    " AND follow_up_id IS NOT NULL AND recall_id IS NULL AND document_id IS NULL)"
    " OR (kind IN ('recall_created', 'recall_updated', 'recall_contacted', 'recall_booked',"
    " 'recall_completed', 'recall_released', 'recall_cancelled') AND appointment_id IS NULL"
    " AND care_item_id IS NULL AND care_session_id IS NULL AND follow_up_id IS NULL"
    " AND recall_id IS NOT NULL AND document_id IS NULL)"
    " OR (kind = 'document_uploaded' AND appointment_id IS NULL AND care_item_id IS NULL"
    " AND care_session_id IS NULL AND follow_up_id IS NULL AND recall_id IS NULL"
    " AND document_id IS NOT NULL)"
)


def upgrade() -> None:
    op.add_column("document", sa.Column("appointment_id", sa.Uuid(), nullable=True))
    op.add_column("document", sa.Column("follow_up_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_document_appointment_id_clinic_id",
        "document",
        "appointment",
        ["appointment_id", "clinic_id"],
        ["id", "clinic_id"],
    )
    op.create_foreign_key(
        "fk_document_follow_up_id_clinic_id",
        "document",
        "follow_up",
        ["follow_up_id", "clinic_id"],
        ["id", "clinic_id"],
    )
    op.create_index("ix_document_clinic_appointment", "document", ["clinic_id", "appointment_id"])
    op.create_index("ix_document_clinic_follow_up", "document", ["clinic_id", "follow_up_id"])

    op.add_column("timeline_event", sa.Column("document_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_timeline_event_document_id_clinic_id",
        "timeline_event",
        "document",
        ["document_id", "clinic_id"],
        ["id", "clinic_id"],
    )
    op.drop_constraint("ck_timeline_event_subject_matches_kind", "timeline_event", type_="check")
    op.drop_constraint("ck_timeline_event_kind_known", "timeline_event", type_="check")
    op.create_check_constraint(
        "ck_timeline_event_kind_known",
        "timeline_event",
        "kind IN (" + ", ".join(f"'{kind}'" for kind in _KINDS) + ")",
    )
    op.create_check_constraint(
        "ck_timeline_event_subject_matches_kind",
        "timeline_event",
        _SUBJECT,
    )


def downgrade() -> None:
    # document_uploaded rows cannot satisfy the previous subject check.
    op.execute("DELETE FROM timeline_event WHERE kind = 'document_uploaded'")
    op.drop_constraint("ck_timeline_event_subject_matches_kind", "timeline_event", type_="check")
    op.drop_constraint("ck_timeline_event_kind_known", "timeline_event", type_="check")
    op.drop_constraint(
        "fk_timeline_event_document_id_clinic_id",
        "timeline_event",
        type_="foreignkey",
    )
    op.drop_column("timeline_event", "document_id")
    op.create_check_constraint(
        "ck_timeline_event_kind_known",
        "timeline_event",
        "kind IN (" + ", ".join(f"'{kind}'" for kind in _KINDS_BEFORE) + ")",
    )
    op.create_check_constraint(
        "ck_timeline_event_subject_matches_kind",
        "timeline_event",
        _SUBJECT_BEFORE,
    )

    op.drop_index("ix_document_clinic_follow_up", table_name="document")
    op.drop_index("ix_document_clinic_appointment", table_name="document")
    op.drop_constraint("fk_document_follow_up_id_clinic_id", "document", type_="foreignkey")
    op.drop_constraint("fk_document_appointment_id_clinic_id", "document", type_="foreignkey")
    op.drop_column("document", "follow_up_id")
    op.drop_column("document", "appointment_id")
