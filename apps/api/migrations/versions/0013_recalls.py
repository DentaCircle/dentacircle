"""Recall interval on the appointment type, and one recall row per patient.

Revision ID: 0013_recalls
Revises: 0012_booked_appointment
Create Date: 2026-10-20

Additive. Downgrade drops recall, then the interval column. The data update only
fills an empty Scaling interval.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_recalls"
down_revision: str | None = "0012_booked_appointment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen at migration time. A later change to domain/recall.py needs a new revision.
_STATUSES = ("scheduled", "contacted", "booked", "completed", "cancelled")
_OPEN = ("booked", "contacted", "scheduled")


def upgrade() -> None:
    op.add_column(
        "appointment_type",
        sa.Column("recall_after_months", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_appointment_type_recall_months_range"),
        "appointment_type",
        "recall_after_months IS NULL OR (recall_after_months BETWEEN 1 AND 60)",
    )
    op.execute(
        "UPDATE appointment_type SET recall_after_months = 6"
        " WHERE recall_after_months IS NULL AND lower(name) = 'scaling'"
    )
    op.create_table(
        "recall",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_type_id", sa.Uuid(), nullable=False),
        sa.Column("source_appointment_id", sa.Uuid(), nullable=False),
        sa.Column("booked_appointment_id", sa.Uuid(), nullable=True),
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
            name=op.f("ck_recall_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_recall_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_recall_patient_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_type.id", "appointment_type.clinic_id"],
            name="fk_recall_appointment_type_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["source_appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_recall_source_appointment_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["booked_appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_recall_booked_appointment_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recall")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_recall_id_clinic_id"),
    )
    op.create_index(op.f("ix_recall_clinic_id"), "recall", ["clinic_id"])
    open_statuses = ", ".join(f"'{status}'" for status in _OPEN)
    op.create_index(
        "uq_recall_open_patient",
        "recall",
        ["clinic_id", "patient_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({open_statuses})"),
    )
    op.create_index(
        "ix_recall_clinic_status_due",
        "recall",
        ["clinic_id", "status", "due_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_recall_clinic_status_due", table_name="recall")
    op.drop_index("uq_recall_open_patient", table_name="recall")
    op.drop_index(op.f("ix_recall_clinic_id"), table_name="recall")
    op.drop_table("recall")
    op.drop_constraint(
        op.f("ck_appointment_type_recall_months_range"),
        "appointment_type",
        type_="check",
    )
    op.drop_column("appointment_type", "recall_after_months")
