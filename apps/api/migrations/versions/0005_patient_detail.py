"""Patient status and the audit field-name list.

Revision ID: 0005_patient_detail
Revises: 0004_patients
Create Date: 2026-10-11

Both columns are new. Existing patients become active. Existing audit rows
leave changed_fields null; new writes set a list.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_patient_detail"
down_revision: str | None = "0004_patients"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patient",
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_patient_status_known",
        "patient",
        "status IN ('active', 'inactive')",
    )
    op.add_column(
        "audit_event",
        sa.Column("changed_fields", sa.ARRAY(sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_event", "changed_fields")
    op.drop_constraint("ck_patient_status_known", "patient", type_="check")
    op.drop_column("patient", "status")
