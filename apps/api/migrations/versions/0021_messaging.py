"""Add messaging contacts and messages without changing existing tables.

Revision ID: 0021_messaging
Revises: 0020_procedure_resource_rules
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_messaging"
down_revision: str | None = "0020_procedure_resource_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE messaging_contact (
            id uuid PRIMARY KEY,
            clinic_id uuid NOT NULL REFERENCES clinic(id),
            patient_id uuid NOT NULL,
            account_key text NOT NULL,
            number text NOT NULL CHECK (number ~ '^\\+[1-9][0-9]{1,14}$'),
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (patient_id, clinic_id) REFERENCES patient(id, clinic_id),
            FOREIGN KEY (created_by_user_id, clinic_id) REFERENCES app_user(id, clinic_id),
            CONSTRAINT uq_messaging_contact_patient UNIQUE (clinic_id, patient_id),
            CONSTRAINT uq_messaging_contact_number UNIQUE (clinic_id, account_key, number),
            CONSTRAINT uq_messaging_contact_account UNIQUE (id, clinic_id, account_key)
        )
    """)
    op.execute("""
        CREATE TABLE message (
            id uuid PRIMARY KEY,
            clinic_id uuid NOT NULL REFERENCES clinic(id),
            contact_id uuid NOT NULL,
            account_key text NOT NULL,
            direction text NOT NULL,
            body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
            state text NOT NULL,
            created_by_user_id uuid,
            request_id uuid,
            provider_message_id text,
            provider_sent_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (contact_id, clinic_id, account_key)
                REFERENCES messaging_contact(id, clinic_id, account_key),
            FOREIGN KEY (created_by_user_id, clinic_id) REFERENCES app_user(id, clinic_id),
            CONSTRAINT uq_message_request UNIQUE (clinic_id, request_id),
            CONSTRAINT uq_message_provider_id UNIQUE (clinic_id, account_key, provider_message_id),
            CHECK (
                (direction = 'inbound' AND state = 'received' AND created_by_user_id IS NULL
                    AND request_id IS NULL AND provider_message_id IS NOT NULL)
                OR (direction = 'outbound' AND state IN ('sending', 'accepted', 'failed', 'unknown')
                    AND created_by_user_id IS NOT NULL AND request_id IS NOT NULL)
            )
        )
    """)
    op.execute(
        "CREATE INDEX ix_message_contact_order ON message "
        "(clinic_id, contact_id, created_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_message_clinic_order ON message (clinic_id, created_at DESC, id DESC)"
    )


def downgrade() -> None:
    op.drop_table("message")
    op.drop_table("messaging_contact")
