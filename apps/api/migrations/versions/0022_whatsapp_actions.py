"""Add message provenance and durable automatic reply claims.

Revision ID: 0022_whatsapp_actions
Revises: 0021_messaging
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_whatsapp_actions"
down_revision: str | None = "0021_messaging"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE message ADD CONSTRAINT uq_message_id_clinic UNIQUE (id, clinic_id)")
    op.execute("ALTER TABLE message ADD COLUMN origin text")
    op.execute(
        "UPDATE message SET origin = CASE WHEN direction = 'inbound' "
        "THEN 'provider' ELSE 'staff' END"
    )
    op.execute("ALTER TABLE message ALTER COLUMN origin SET NOT NULL")
    op.execute("ALTER TABLE message ADD COLUMN caused_by_message_id uuid")
    op.execute("ALTER TABLE message ADD COLUMN dispatch_order bigint GENERATED ALWAYS AS IDENTITY")
    op.execute("ALTER TABLE message ADD COLUMN dispatch_owner uuid")
    op.execute("ALTER TABLE message ADD COLUMN dispatch_deadline_at timestamptz")
    op.execute(
        "ALTER TABLE message ADD CONSTRAINT fk_message_cause "
        "FOREIGN KEY (caused_by_message_id, clinic_id) REFERENCES message(id, clinic_id)"
    )
    op.execute(
        "ALTER TABLE message ADD CONSTRAINT uq_message_cause "
        "UNIQUE (clinic_id, caused_by_message_id)"
    )
    op.execute("ALTER TABLE message DROP CONSTRAINT message_check")
    op.execute("""
        ALTER TABLE message ADD CONSTRAINT ck_message_direction_state_actor CHECK (
          (origin = 'provider' AND direction = 'inbound' AND state = 'received'
           AND created_by_user_id IS NULL AND request_id IS NULL
           AND provider_message_id IS NOT NULL AND caused_by_message_id IS NULL)
          OR (origin = 'staff' AND direction = 'outbound'
           AND state IN ('sending', 'accepted', 'failed', 'unknown')
           AND created_by_user_id IS NOT NULL AND request_id IS NOT NULL
           AND caused_by_message_id IS NULL)
          OR (origin = 'automation' AND direction = 'outbound'
           AND state IN ('queued', 'sending', 'accepted', 'failed', 'unknown', 'superseded')
           AND created_by_user_id IS NULL AND request_id IS NULL
           AND caused_by_message_id IS NOT NULL)
        )
    """)
    op.execute(
        "ALTER TABLE message ADD CONSTRAINT ck_message_dispatch_claim CHECK "
        "((origin = 'automation' AND state = 'sending' "
        "AND dispatch_owner IS NOT NULL AND dispatch_deadline_at IS NOT NULL) OR "
        "((origin != 'automation' OR state != 'sending') AND dispatch_owner IS NULL "
        "AND dispatch_deadline_at IS NULL))"
    )
    op.execute(
        "CREATE INDEX ix_message_dispatch_order ON message (clinic_id, contact_id, dispatch_order)"
    )
    op.execute(
        "CREATE INDEX ix_message_dispatch_claim ON message "
        "(clinic_id, contact_id, dispatch_deadline_at) "
        "WHERE state = 'sending' AND dispatch_owner IS NOT NULL"
    )
    for table in ("audit_event", "timeline_event"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN actor_kind text NOT NULL DEFAULT 'staff'")
        op.execute(f"ALTER TABLE {table} ADD COLUMN actor_message_id uuid")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN actor_user_id DROP NOT NULL")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_actor_message "
            "FOREIGN KEY (actor_message_id, clinic_id) REFERENCES message(id, clinic_id)"
        )
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_actor CHECK "
            "((actor_kind = 'staff' AND actor_user_id IS NOT NULL AND actor_message_id IS NULL) "
            "OR (actor_kind = 'whatsapp' AND actor_user_id IS NULL "
            "AND actor_message_id IS NOT NULL))"
        )


def downgrade() -> None:
    for table in ("timeline_event", "audit_event"):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT ck_{table}_actor")
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT fk_{table}_actor_message")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN actor_user_id SET NOT NULL")
        op.execute(f"ALTER TABLE {table} DROP COLUMN actor_message_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN actor_kind")
    op.execute("DROP INDEX ix_message_dispatch_claim")
    op.execute("DROP INDEX ix_message_dispatch_order")
    op.execute("ALTER TABLE message DROP CONSTRAINT ck_message_dispatch_claim")
    op.execute("ALTER TABLE message DROP CONSTRAINT ck_message_direction_state_actor")
    op.execute("""ALTER TABLE message ADD CONSTRAINT message_check CHECK (
        (direction = 'inbound' AND state = 'received' AND created_by_user_id IS NULL
         AND request_id IS NULL AND provider_message_id IS NOT NULL)
        OR (direction = 'outbound' AND state IN ('sending', 'accepted', 'failed', 'unknown')
         AND created_by_user_id IS NOT NULL AND request_id IS NOT NULL))""")
    op.execute("ALTER TABLE message DROP CONSTRAINT uq_message_cause")
    op.execute("ALTER TABLE message DROP CONSTRAINT fk_message_cause")
    op.execute(
        "ALTER TABLE message DROP COLUMN dispatch_deadline_at, DROP COLUMN dispatch_owner, "
        "DROP COLUMN dispatch_order, DROP COLUMN caused_by_message_id, DROP COLUMN origin"
    )
    op.execute("ALTER TABLE message DROP CONSTRAINT uq_message_id_clinic")
