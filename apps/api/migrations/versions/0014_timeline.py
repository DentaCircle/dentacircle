"""Patient timeline events. Additive. No backfill.

Revision ID: 0014_timeline
Revises: 0013_recalls
Create Date: 2026-10-20

Downgrade drops the table. Kind names are frozen here. A later kind needs a new revision.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_timeline"
down_revision: str | None = "0013_recalls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS = (
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

_SUBJECT = (
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


def upgrade() -> None:
    op.create_table(
        "timeline_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("appointment_id", sa.Uuid(), nullable=True),
        sa.Column("care_item_id", sa.Uuid(), nullable=True),
        sa.Column("care_session_id", sa.Uuid(), nullable=True),
        sa.Column("follow_up_id", sa.Uuid(), nullable=True),
        sa.Column("recall_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{kind}'" for kind in _KINDS) + ")",
            name="ck_timeline_event_kind_known",
        ),
        sa.CheckConstraint(_SUBJECT, name="ck_timeline_event_subject_matches_kind"),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_timeline_event_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "actor_user_id"],
            ["app_user.clinic_id", "app_user.id"],
            name="fk_timeline_event_clinic_id_actor_user_id",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_timeline_event_patient_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_timeline_event_appointment_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["care_item_id", "clinic_id"],
            ["care_item.id", "care_item.clinic_id"],
            name="fk_timeline_event_care_item_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["care_session_id", "clinic_id"],
            ["care_session.id", "care_session.clinic_id"],
            name="fk_timeline_event_care_session_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["follow_up_id", "clinic_id"],
            ["follow_up.id", "follow_up.clinic_id"],
            name="fk_timeline_event_follow_up_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["recall_id", "clinic_id"],
            ["recall.id", "recall.clinic_id"],
            name="fk_timeline_event_recall_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_timeline_event")),
    )
    op.execute(
        "CREATE INDEX ix_timeline_event_patient_order ON timeline_event"
        " (clinic_id, patient_id, occurred_at DESC, seq DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_timeline_event_patient_order")
    op.drop_table("timeline_event")
