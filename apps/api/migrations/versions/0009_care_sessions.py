"""Care sessions recorded against one visit.

Revision ID: 0009_care_sessions
Revises: 0008_care_plans
Create Date: 2026-10-17

Adds care_session and care_session_item. Also adds unique (id, clinic_id) on
appointment and care_item so the new composite foreign keys can stay in one clinic.
Those two constraints add no columns. id is already the primary key, so they cannot
fail on existing rows. Downgrade drops the new tables and those two constraints.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_care_sessions"
down_revision: str | None = "0008_care_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen at migration time. A later change to domain/care_session.py needs a new revision.
_RESULTS = ("started", "completed")


def upgrade() -> None:
    op.create_unique_constraint("uq_appointment_id_clinic_id", "appointment", ["id", "clinic_id"])
    op.create_unique_constraint("uq_care_item_id_clinic_id", "care_item", ["id", "clinic_id"])
    op.create_table(
        "care_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_care_session_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_care_session_appointment_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_care_session_patient_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "recorded_by_user_id"],
            ["app_user.clinic_id", "app_user.id"],
            name="fk_care_session_recorded_by_user_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_care_session")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_care_session_id_clinic_id"),
        sa.UniqueConstraint(
            "clinic_id", "appointment_id", name="uq_care_session_clinic_appointment"
        ),
    )
    op.create_index(op.f("ix_care_session_clinic_id"), "care_session", ["clinic_id"])
    op.create_index(
        "ix_care_session_clinic_patient_created",
        "care_session",
        ["clinic_id", "patient_id", "created_at"],
    )
    op.create_table(
        "care_session_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("care_session_id", sa.Uuid(), nullable=False),
        sa.Column("care_item_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{status}'" for status in _RESULTS) + ")",
            name=op.f("ck_care_session_item_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_care_session_item_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["care_session_id", "clinic_id"],
            ["care_session.id", "care_session.clinic_id"],
            name="fk_care_session_item_session_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["care_item_id", "clinic_id"],
            ["care_item.id", "care_item.clinic_id"],
            name="fk_care_session_item_care_item_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_care_session_item")),
        sa.UniqueConstraint(
            "care_session_id",
            "care_item_id",
            name="uq_care_session_item_session_item",
        ),
    )
    op.create_index(op.f("ix_care_session_item_clinic_id"), "care_session_item", ["clinic_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_care_session_item_clinic_id"), table_name="care_session_item")
    op.drop_table("care_session_item")
    op.drop_index("ix_care_session_clinic_patient_created", table_name="care_session")
    op.drop_index(op.f("ix_care_session_clinic_id"), table_name="care_session")
    op.drop_table("care_session")
    op.drop_constraint("uq_care_item_id_clinic_id", "care_item", type_="unique")
    op.drop_constraint("uq_appointment_id_clinic_id", "appointment", type_="unique")
