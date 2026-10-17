"""One follow-up row per patient while unfinished care is still open.

Revision ID: 0010_follow_ups
Revises: 0009_care_sessions
Create Date: 2026-10-17

Additive. Downgrade drops follow_up and nothing else.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_follow_ups"
down_revision: str | None = "0009_care_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen at migration time. A later change to domain/follow_up.py needs a new revision.
_STATUSES = ("scheduled", "contacted", "booked", "completed", "cancelled")
_OPEN = ("booked", "contacted", "scheduled")


def upgrade() -> None:
    op.create_table(
        "follow_up",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'scheduled'"), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{status}'" for status in _STATUSES) + ")",
            name=op.f("ck_follow_up_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_follow_up_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_follow_up_patient_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_follow_up_appointment_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_follow_up")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_follow_up_id_clinic_id"),
    )
    op.create_index(op.f("ix_follow_up_clinic_id"), "follow_up", ["clinic_id"])
    open_statuses = ", ".join(f"'{status}'" for status in _OPEN)
    op.create_index(
        "uq_follow_up_open_patient",
        "follow_up",
        ["clinic_id", "patient_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({open_statuses})"),
    )
    op.create_index(
        "ix_follow_up_clinic_status_due",
        "follow_up",
        ["clinic_id", "status", "due_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_follow_up_clinic_status_due", table_name="follow_up")
    op.drop_index("uq_follow_up_open_patient", table_name="follow_up")
    op.drop_index(op.f("ix_follow_up_clinic_id"), table_name="follow_up")
    op.drop_table("follow_up")
