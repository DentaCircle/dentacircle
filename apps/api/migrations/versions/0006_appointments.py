"""Appointments, with one blocking visit per clinician at a time.

Revision ID: 0006_appointments
Revises: 0005_patient_detail
Create Date: 2026-10-11

Additive. btree_gist already exists from 0003_clinic_day. Downgrade drops the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_appointments"
down_revision: str | None = "0005_patient_detail"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen at migration time. A later change to domain/appointment.py needs a new revision.
_STATUSES = ("scheduled", "arrived", "in_progress", "completed", "cancelled", "no_show")


def upgrade() -> None:
    op.create_table(
        "appointment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("clinician_user_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_type_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'scheduled'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ends_at > starts_at",
            name=op.f("ck_appointment_ends_after_start"),
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{status}'" for status in _STATUSES) + ")",
            name=op.f("ck_appointment_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_appointment_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_appointment_patient_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_type.id", "appointment_type.clinic_id"],
            name="fk_appointment_type_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "clinician_user_id"],
            ["app_user.clinic_id", "app_user.id"],
            name="fk_appointment_clinician_user_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointment")),
    )
    op.create_index(op.f("ix_appointment_clinic_id"), "appointment", ["clinic_id"])
    op.create_index(
        "ix_appointment_clinic_patient_starts",
        "appointment",
        ["clinic_id", "patient_id", "starts_at"],
    )
    op.create_index(
        "ix_appointment_clinic_starts",
        "appointment",
        ["clinic_id", "starts_at"],
    )
    op.execute(
        "ALTER TABLE appointment ADD CONSTRAINT ex_appointment_no_overlap "
        "EXCLUDE USING gist ("
        "clinic_id WITH =, "
        "clinician_user_id WITH =, "
        "tstzrange(starts_at, ends_at, '[)') WITH &&) "
        "WHERE (status NOT IN ('cancelled', 'no_show'))"
    )


def downgrade() -> None:
    op.drop_index("ix_appointment_clinic_starts", table_name="appointment")
    op.drop_index("ix_appointment_clinic_patient_starts", table_name="appointment")
    op.drop_index(op.f("ix_appointment_clinic_id"), table_name="appointment")
    op.drop_table("appointment")
