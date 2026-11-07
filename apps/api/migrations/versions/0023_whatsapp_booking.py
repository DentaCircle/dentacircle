"""Persist WhatsApp booking sessions and automation controls.

Revision ID: 0023_whatsapp_booking
Revises: 0022_whatsapp_actions
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023_whatsapp_booking"
down_revision: str | None = "0022_whatsapp_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE messaging_contact ADD COLUMN automation_state text NOT NULL DEFAULT 'active'"
    )
    op.execute(
        "ALTER TABLE messaging_contact ADD COLUMN automation_version integer NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE messaging_contact ADD COLUMN automation_changed_at timestamptz")
    op.execute("UPDATE messaging_contact SET automation_changed_at = created_at")
    op.execute("ALTER TABLE messaging_contact ALTER COLUMN automation_changed_at SET NOT NULL")
    op.execute("ALTER TABLE messaging_contact ALTER COLUMN automation_changed_at SET DEFAULT now()")
    op.execute("""ALTER TABLE messaging_contact ADD CONSTRAINT ck_contact_automation_state
        CHECK (automation_state IN ('active', 'needs_staff', 'staff_handling', 'stopped'))""")
    op.execute("""ALTER TABLE messaging_contact ADD CONSTRAINT ck_contact_automation_version
        CHECK (automation_version >= 0)""")
    op.execute("""CREATE TABLE whatsapp_booking_session (
        id uuid PRIMARY KEY, clinic_id uuid NOT NULL REFERENCES clinic(id),
        contact_id uuid NOT NULL, account_key text NOT NULL,
        state text NOT NULL CHECK (state IN ('resume_challenge', 'visits', 'source', 'type',
            'slots', 'confirmation', 'booked', 'stopped', 'expired')),
        menu_version integer NOT NULL DEFAULT 0 CHECK (menu_version >= 0),
        menu_token text NOT NULL,
        automation_version integer NOT NULL CHECK (automation_version >= 0),
        choices jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(choices) = 'object'),
        acknowledged_visits jsonb NOT NULL DEFAULT '[]'::jsonb
            CHECK (jsonb_typeof(acknowledged_visits) = 'array'),
        appointment_type_id uuid, clinician_user_id uuid, selected_date date,
        follow_up_id uuid, recall_id uuid, booked_appointment_id uuid,
        expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_booking_session_id_clinic UNIQUE (id, clinic_id),
        CONSTRAINT uq_booking_menu_token UNIQUE (menu_token),
        CONSTRAINT uq_booking_appointment UNIQUE (clinic_id, booked_appointment_id),
        CONSTRAINT ck_booking_one_source CHECK (follow_up_id IS NULL OR recall_id IS NULL),
        CONSTRAINT ck_booking_menu_token CHECK (menu_token ~ '^[A-Z0-9]{4,12}$'),
        CONSTRAINT ck_booking_choice_shapes CHECK (
            (NOT (choices ? 'entries') OR jsonb_typeof(choices->'entries') = 'array') AND
            (NOT (choices ? 'visits') OR jsonb_typeof(choices->'visits') = 'array') AND
            (NOT (choices ? 'display') OR jsonb_typeof(choices->'display') = 'array') AND
            (NOT (choices ? 'selected') OR jsonb_typeof(choices->'selected') = 'object') AND
            (NOT (choices ? 'title') OR jsonb_typeof(choices->'title') = 'string') AND
            (NOT (choices ? 'cursor') OR jsonb_typeof(choices->'cursor') = 'number') AND
            (NOT (choices ? 'next_cursor') OR jsonb_typeof(choices->'next_cursor') = 'number') AND
            (NOT (choices ? 'count') OR jsonb_typeof(choices->'count') = 'number')
        ),
        CONSTRAINT fk_booking_contact FOREIGN KEY (contact_id, clinic_id, account_key)
            REFERENCES messaging_contact(id, clinic_id, account_key),
        CONSTRAINT fk_booking_type FOREIGN KEY (appointment_type_id, clinic_id)
            REFERENCES appointment_type(id, clinic_id),
        CONSTRAINT fk_booking_clinician FOREIGN KEY (clinician_user_id, clinic_id)
            REFERENCES app_user(id, clinic_id),
        CONSTRAINT fk_booking_follow_up FOREIGN KEY (follow_up_id, clinic_id)
            REFERENCES follow_up(id, clinic_id),
        CONSTRAINT fk_booking_recall FOREIGN KEY (recall_id, clinic_id)
            REFERENCES recall(id, clinic_id),
        CONSTRAINT fk_booking_appointment FOREIGN KEY (booked_appointment_id, clinic_id)
            REFERENCES appointment(id, clinic_id)
    )""")
    op.execute("""CREATE UNIQUE INDEX uq_booking_active_contact
        ON whatsapp_booking_session (clinic_id, contact_id, account_key)
        WHERE state IN ('resume_challenge', 'visits', 'source', 'type', 'slots', 'confirmation')""")
    op.execute("""CREATE INDEX ix_booking_contact_history
        ON whatsapp_booking_session (clinic_id, contact_id, created_at DESC)""")
    op.execute("ALTER TABLE message ADD COLUMN purpose text")
    op.execute("UPDATE message SET purpose = 'chat' WHERE origin = 'staff'")
    op.execute("ALTER TABLE message ADD COLUMN booking_session_id uuid")
    op.execute("ALTER TABLE message ADD COLUMN menu_version integer")
    op.execute("ALTER TABLE message ADD COLUMN automation_version integer")
    op.execute("ALTER TABLE message ADD COLUMN reply_kind text")
    op.execute("""ALTER TABLE message ADD CONSTRAINT fk_message_booking_session
        FOREIGN KEY (booking_session_id, clinic_id)
        REFERENCES whatsapp_booking_session(id, clinic_id)
    """)
    op.execute("""ALTER TABLE message ADD CONSTRAINT ck_message_booking_metadata CHECK (
        (origin = 'staff' AND purpose IS NOT NULL AND purpose IN ('chat', 'booking_invitation')
         AND booking_session_id IS NULL AND menu_version IS NULL AND automation_version IS NULL
         AND reply_kind IS NULL)
        OR (origin = 'provider' AND purpose IS NULL AND booking_session_id IS NULL
         AND menu_version IS NULL AND automation_version IS NULL AND reply_kind IS NULL)
        OR (origin = 'automation' AND purpose IS NULL AND (
          (booking_session_id IS NULL AND menu_version IS NULL AND automation_version IS NULL
           AND reply_kind IS NULL)
          OR (booking_session_id IS NULL AND menu_version IS NULL
           AND automation_version IS NOT NULL AND reply_kind = 'menu')
          OR (booking_session_id IS NOT NULL AND menu_version IS NOT NULL
           AND automation_version IS NOT NULL AND reply_kind IS NOT NULL
           AND reply_kind IN ('menu', 'result', 'control_ack', 'resume_challenge'))))
    )""")
    op.execute("""CREATE INDEX ix_message_booking_workflow
        ON message (clinic_id, booking_session_id, reply_kind, state)""")


def downgrade() -> None:
    op.execute("DROP INDEX ix_message_booking_workflow")
    op.execute("""ALTER TABLE message DROP CONSTRAINT ck_message_booking_metadata,
        DROP CONSTRAINT fk_message_booking_session""")
    op.execute("""ALTER TABLE message DROP COLUMN reply_kind, DROP COLUMN automation_version,
        DROP COLUMN menu_version, DROP COLUMN booking_session_id, DROP COLUMN purpose""")
    op.execute("DROP TABLE whatsapp_booking_session")
    op.execute("""ALTER TABLE messaging_contact DROP CONSTRAINT ck_contact_automation_state,
        DROP CONSTRAINT ck_contact_automation_version""")
    op.execute("""ALTER TABLE messaging_contact DROP COLUMN automation_changed_at,
        DROP COLUMN automation_version, DROP COLUMN automation_state""")
