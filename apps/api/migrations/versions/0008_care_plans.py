"""Care plans and care items.

Revision ID: 0008_care_plans
Revises: 0007_patient_overlap
Create Date: 2026-10-15

Additive. Downgrade drops the two tables and nothing else.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_care_plans"
down_revision: str | None = "0007_patient_overlap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen at migration time. A later change to domain/care.py needs a new revision.
_STATUSES = ("planned", "started", "completed", "cancelled")


def upgrade() -> None:
    op.create_table(
        "care_plan",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_care_plan_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_care_plan_patient_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_care_plan")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_care_plan_id_clinic_id"),
    )
    op.create_index(op.f("ix_care_plan_clinic_id"), "care_plan", ["clinic_id"])
    op.create_index(
        "ix_care_plan_clinic_patient_created",
        "care_plan",
        ["clinic_id", "patient_id", "created_at"],
    )
    op.create_table(
        "care_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("care_plan_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{status}'" for status in _STATUSES) + ")",
            name=op.f("ck_care_item_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_care_item_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["care_plan_id", "clinic_id"],
            ["care_plan.id", "care_plan.clinic_id"],
            name="fk_care_item_care_plan_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_care_item")),
    )
    op.create_index(op.f("ix_care_item_clinic_id"), "care_item", ["clinic_id"])
    op.create_index(
        "ix_care_item_clinic_plan_created",
        "care_item",
        ["clinic_id", "care_plan_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_care_item_clinic_plan_created", table_name="care_item")
    op.drop_index(op.f("ix_care_item_clinic_id"), table_name="care_item")
    op.drop_table("care_item")
    op.drop_index("ix_care_plan_clinic_patient_created", table_name="care_plan")
    op.drop_index(op.f("ix_care_plan_clinic_id"), table_name="care_plan")
    op.drop_table("care_plan")
