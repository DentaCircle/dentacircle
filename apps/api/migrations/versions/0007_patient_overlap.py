"""One blocking visit per patient at a time.

Revision ID: 0007_patient_overlap
Revises: 0006_appointments
Create Date: 2026-10-14

Additive. btree_gist already exists. Downgrade drops only this constraint.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_patient_overlap"
down_revision: str | None = "0006_appointments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conflicts = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT a.id::text, b.id::text"
                " FROM appointment AS a"
                " JOIN appointment AS b"
                " ON a.clinic_id = b.clinic_id"
                " AND a.patient_id = b.patient_id"
                " AND a.id < b.id"
                " AND tstzrange(a.starts_at, a.ends_at, '[)')"
                " && tstzrange(b.starts_at, b.ends_at, '[)')"
                " WHERE a.status NOT IN ('cancelled', 'no_show')"
                " AND b.status NOT IN ('cancelled', 'no_show')"
            )
        )
        .all()
    )
    if conflicts:
        pairs = "; ".join(f"{left} overlaps {right}" for left, right in conflicts)
        raise RuntimeError(
            "Cannot add ex_appointment_patient_no_overlap. Fix these appointments first: " + pairs
        )
    op.execute(
        "ALTER TABLE appointment ADD CONSTRAINT ex_appointment_patient_no_overlap "
        "EXCLUDE USING gist ("
        "clinic_id WITH =, "
        "patient_id WITH =, "
        "tstzrange(starts_at, ends_at, '[)') WITH &&) "
        "WHERE (status NOT IN ('cancelled', 'no_show'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE appointment DROP CONSTRAINT ex_appointment_patient_no_overlap")
