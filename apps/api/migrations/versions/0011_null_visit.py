"""Allow a follow-up with no visit.

Revision ID: 0011_null_visit
Revises: 0010_follow_ups
Create Date: 2026-10-17

Relaxes one column. Downgrade refuses while any row has a null appointment_id.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_null_visit"
down_revision: str | None = "0010_follow_ups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("follow_up", "appointment_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    missing = bind.execute(
        sa.text("SELECT 1 FROM follow_up WHERE appointment_id IS NULL LIMIT 1")
    ).first()
    if missing is not None:
        raise RuntimeError(
            "follow_up.appointment_id cannot be set NOT NULL while a row has no visit"
        )
    op.alter_column("follow_up", "appointment_id", existing_type=sa.Uuid(), nullable=False)
