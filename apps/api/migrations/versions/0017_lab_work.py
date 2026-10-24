"""Lab work, a document link, and the lab timeline kinds.

Revision ID: 0017_lab_work
Revises: 0016_document_links
Create Date: 2026-10-24

Adds the lab_work table, a nullable lab_work_id on document, and lab_work_id on
timeline_event. Drops and recreates the timeline kind and subject checks so the
four lab kinds are allowed with that one subject. Existing rows stay valid:
their new columns are null.

Downgrade deletes lab timeline rows first, then restores the previous checks.
It clears document.lab_work_id and drops the new columns and the lab_work table.
Those timeline rows and lab items are not restored.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_lab_work"
down_revision: str | None = "0016_document_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = ("pending", "ready", "collected", "cancelled")
_LAB_KINDS = (
    "lab_work_created",
    "lab_work_ready",
    "lab_work_collected",
    "lab_work_cancelled",
)
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
    "document_uploaded",
)
_KINDS = _KINDS_BEFORE + _LAB_KINDS
_COLUMNS_BEFORE = (
    "appointment_id",
    "care_item_id",
    "care_session_id",
    "follow_up_id",
    "recall_id",
    "document_id",
)
_COLUMNS = _COLUMNS_BEFORE + ("lab_work_id",)
_VISIT_KINDS = (
    "visit_booked",
    "visit_rescheduled",
    "visit_cancelled",
    "visit_arrived",
    "visit_started",
    "visit_completed",
    "visit_no_show",
)
_CARE_ITEM_KINDS = (
    "care_item_added",
    "care_item_started",
    "care_item_completed",
    "care_item_cancelled",
)
_FOLLOW_UP_KINDS = (
    "follow_up_created",
    "follow_up_updated",
    "follow_up_contacted",
    "follow_up_booked",
    "follow_up_completed",
    "follow_up_released",
    "follow_up_cancelled",
)
_RECALL_KINDS = (
    "recall_created",
    "recall_updated",
    "recall_contacted",
    "recall_booked",
    "recall_completed",
    "recall_released",
    "recall_cancelled",
)


def _only(column: str, columns: tuple[str, ...]) -> str:
    parts = [f"{name} IS {'NOT NULL' if name == column else 'NULL'}" for name in columns]
    return " AND ".join(parts)


def _group(names: tuple[str, ...], column: str, columns: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{name}'" for name in names)
    return f"(kind IN ({listed}) AND {_only(column, columns)})"


def _subject_sql(columns: tuple[str, ...], *, with_lab: bool) -> str:
    clauses = [
        "(kind = 'patient_registered' AND "
        + " AND ".join(f"{name} IS NULL" for name in columns)
        + ")",
        _group(_VISIT_KINDS, "appointment_id", columns),
        _group(_CARE_ITEM_KINDS, "care_item_id", columns),
        "(kind = 'care_session_recorded' AND " + _only("care_session_id", columns) + ")",
        _group(_FOLLOW_UP_KINDS, "follow_up_id", columns),
        _group(_RECALL_KINDS, "recall_id", columns),
        "(kind = 'document_uploaded' AND " + _only("document_id", columns) + ")",
    ]
    if with_lab:
        clauses.append(_group(_LAB_KINDS, "lab_work_id", columns))
    return " OR ".join(clauses)


def _kind_sql(kinds: tuple[str, ...]) -> str:
    return "kind IN (" + ", ".join(f"'{kind}'" for kind in kinds) + ")"


def upgrade() -> None:
    op.create_table(
        "lab_work",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("expected_on", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{status}'" for status in _STATUSES) + ")",
            name=op.f("ck_lab_work_status_known"),
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200",
            name=op.f("ck_lab_work_title_length"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_lab_work_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_lab_work_patient_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_lab_work_appointment_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id", "clinic_id"],
            ["app_user.id", "app_user.clinic_id"],
            name="fk_lab_work_created_by_user_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lab_work")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_lab_work_id_clinic_id"),
    )
    op.create_index(op.f("ix_lab_work_clinic_id"), "lab_work", ["clinic_id"])
    op.create_index(
        "ix_lab_work_clinic_status_expected",
        "lab_work",
        ["clinic_id", "status", "expected_on"],
    )
    op.execute(
        "CREATE INDEX ix_lab_work_patient_order ON lab_work"
        " (clinic_id, patient_id, created_at DESC, id DESC)"
    )

    op.add_column("document", sa.Column("lab_work_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_document_lab_work_id_clinic_id",
        "document",
        "lab_work",
        ["lab_work_id", "clinic_id"],
        ["id", "clinic_id"],
    )
    op.create_index("ix_document_clinic_lab_work", "document", ["clinic_id", "lab_work_id"])

    op.add_column("timeline_event", sa.Column("lab_work_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_timeline_event_lab_work_id_clinic_id",
        "timeline_event",
        "lab_work",
        ["lab_work_id", "clinic_id"],
        ["id", "clinic_id"],
    )
    op.drop_constraint("ck_timeline_event_subject_matches_kind", "timeline_event", type_="check")
    op.drop_constraint("ck_timeline_event_kind_known", "timeline_event", type_="check")
    op.create_check_constraint(
        "ck_timeline_event_kind_known",
        "timeline_event",
        _kind_sql(_KINDS),
    )
    op.create_check_constraint(
        "ck_timeline_event_subject_matches_kind",
        "timeline_event",
        _subject_sql(_COLUMNS, with_lab=True),
    )


def downgrade() -> None:
    # Lab kinds cannot satisfy the previous subject check.
    listed = ", ".join(f"'{kind}'" for kind in _LAB_KINDS)
    op.execute(f"DELETE FROM timeline_event WHERE kind IN ({listed})")
    op.drop_constraint("ck_timeline_event_subject_matches_kind", "timeline_event", type_="check")
    op.drop_constraint("ck_timeline_event_kind_known", "timeline_event", type_="check")
    op.drop_constraint(
        "fk_timeline_event_lab_work_id_clinic_id",
        "timeline_event",
        type_="foreignkey",
    )
    op.drop_column("timeline_event", "lab_work_id")
    op.create_check_constraint(
        "ck_timeline_event_kind_known",
        "timeline_event",
        _kind_sql(_KINDS_BEFORE),
    )
    op.create_check_constraint(
        "ck_timeline_event_subject_matches_kind",
        "timeline_event",
        _subject_sql(_COLUMNS_BEFORE, with_lab=False),
    )

    op.execute("UPDATE document SET lab_work_id = NULL")
    op.drop_index("ix_document_clinic_lab_work", table_name="document")
    op.drop_constraint("fk_document_lab_work_id_clinic_id", "document", type_="foreignkey")
    op.drop_column("document", "lab_work_id")

    op.execute("DROP INDEX IF EXISTS ix_lab_work_patient_order")
    op.drop_index("ix_lab_work_clinic_status_expected", table_name="lab_work")
    op.drop_index(op.f("ix_lab_work_clinic_id"), table_name="lab_work")
    op.drop_table("lab_work")
