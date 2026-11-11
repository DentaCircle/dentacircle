"""Add manually scheduled appointment reminders.

Revision ID: 0024_reminders
Revises: 0023_whatsapp_booking
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_reminders"
down_revision: str | None = "0023_whatsapp_booking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""CREATE TABLE reminder (
        id uuid PRIMARY KEY,
        clinic_id uuid NOT NULL REFERENCES clinic(id),
        appointment_id uuid NOT NULL,
        due_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        resolved_at timestamptz,
        status text NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'completed', 'cancelled')),
        CONSTRAINT fk_reminder_appointment_clinic
            FOREIGN KEY (appointment_id, clinic_id) REFERENCES appointment(id, clinic_id)
    )""")
    op.execute("""CREATE UNIQUE INDEX uq_reminder_pending_appointment
        ON reminder (clinic_id, appointment_id) WHERE status = 'pending'""")
    op.execute("""CREATE INDEX ix_reminder_pending_due
        ON reminder (clinic_id, due_at, id) WHERE status = 'pending'""")


def downgrade() -> None:
    op.execute("DROP TABLE reminder")
