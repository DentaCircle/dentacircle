"""Patients, per-clinic numbers, and audit events.

Revision ID: 0004_patients
Revises: 0003_clinic_day
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_patients"
down_revision: str | None = "0003_clinic_day"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen at migration time. A later change to domain/audit.py needs a new revision.
_AUDIT_ACTIONS = ("create", "update", "status_change", "delete")


def upgrade() -> None:
    op.create_table(
        "patient_number_counter",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_patient_number_counter_clinic_id_clinic"),
        ),
        sa.PrimaryKeyConstraint("clinic_id", name=op.f("pk_patient_number_counter")),
    )
    op.create_table(
        "patient",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_number", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("phone_digits", sa.String(length=15), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(phone_digits) BETWEEN 7 AND 15",
            name=op.f("ck_patient_phone_digits_length"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinic.id"], name=op.f("fk_patient_clinic_id_clinic")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_patient_id_clinic_id"),
        sa.UniqueConstraint(
            "clinic_id", "patient_number", name="uq_patient_clinic_id_patient_number"
        ),
    )
    op.create_index(op.f("ix_patient_clinic_id"), "patient", ["clinic_id"])
    op.create_index(
        "ix_patient_clinic_lower_full_name",
        "patient",
        ["clinic_id", sa.text("lower(full_name)")],
    )
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN (" + ", ".join(f"'{action}'" for action in _AUDIT_ACTIONS) + ")",
            name=op.f("ck_audit_event_action_known"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinic.id"], name=op.f("fk_audit_event_clinic_id_clinic")
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "actor_user_id"],
            ["app_user.clinic_id", "app_user.id"],
            name="fk_audit_event_clinic_id_app_user",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_event")),
    )
    op.create_index(
        "ix_audit_event_entity",
        "audit_event",
        ["clinic_id", "entity_type", "entity_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_event_occurred",
        "audit_event",
        ["clinic_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_event_occurred", table_name="audit_event")
    op.drop_index("ix_audit_event_entity", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_index("ix_patient_clinic_lower_full_name", table_name="patient")
    op.drop_index(op.f("ix_patient_clinic_id"), table_name="patient")
    op.drop_table("patient")
    op.drop_table("patient_number_counter")
