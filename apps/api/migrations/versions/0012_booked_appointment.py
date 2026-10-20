"""Store the visit booked from a follow-up.

Revision ID: 0012_booked_appointment
Revises: 0011_null_visit
Create Date: 2026-10-20

Additive. Downgrade drops the column and its clinic-scoped foreign key.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_booked_appointment"
down_revision: str | None = "0011_null_visit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("follow_up", sa.Column("booked_appointment_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_follow_up_booked_appointment_id_clinic_id",
        "follow_up",
        "appointment",
        ["booked_appointment_id", "clinic_id"],
        ["id", "clinic_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_follow_up_booked_appointment_id_clinic_id",
        "follow_up",
        type_="foreignkey",
    )
    op.drop_column("follow_up", "booked_appointment_id")
