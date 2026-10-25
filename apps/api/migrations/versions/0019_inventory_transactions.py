"""Append-only inventory transactions.

Revision ID: 0019_inventory_transactions
Revises: 0018_inventory
Create Date: 2026-10-25

One new table. A row records a restock or an adjustment. Stock is the sum
of quantity_change. No existing table changes. A trigger rejects UPDATE
and DELETE so a mistake is fixed with another row.

Downgrade drops the table, its triggers and the function. Rows are not restored.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_inventory_transactions"
down_revision: str | None = "0018_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = ("restock", "adjustment")
_REASONS = ("damaged", "expired", "correction")
_SIGN = (
    "(type = 'restock' AND quantity_change > 0 AND reason IS NULL) OR "
    "(type = 'adjustment' AND reason IS NOT NULL AND reason IN ("
    + ", ".join(f"'{reason}'" for reason in _REASONS)
    + ") AND (reason = 'correction' OR quantity_change < 0))"
)


def upgrade() -> None:
    op.create_table(
        "inventory_transaction",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("quantity_change", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN (" + ", ".join(f"'{name}'" for name in _TYPES) + ")",
            name=op.f("ck_inventory_transaction_type_known"),
        ),
        sa.CheckConstraint(
            "quantity_change <> 0 AND quantity_change BETWEEN -1000000 AND 1000000",
            name=op.f("ck_inventory_transaction_quantity_range"),
        ),
        sa.CheckConstraint(_SIGN, name=op.f("ck_inventory_transaction_type_reason_sign")),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_inventory_transaction_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "clinic_id"],
            ["inventory_batch.id", "inventory_batch.clinic_id"],
            name="fk_inventory_transaction_batch_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id", "clinic_id"],
            ["app_user.id", "app_user.clinic_id"],
            name="fk_inventory_transaction_created_by_user_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_transaction")),
    )
    op.create_index(
        op.f("ix_inventory_transaction_clinic_id"),
        "inventory_transaction",
        ["clinic_id"],
    )
    op.execute(
        "CREATE INDEX ix_inventory_transaction_clinic_batch_created"
        " ON inventory_transaction (clinic_id, batch_id, created_at DESC)"
    )
    op.execute(
        """
        CREATE FUNCTION inventory_transaction_refuse_change() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'inventory_transaction is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER inventory_transaction_no_update
        BEFORE UPDATE ON inventory_transaction
        FOR EACH ROW
        EXECUTE FUNCTION inventory_transaction_refuse_change()
        """
    )
    op.execute(
        """
        CREATE TRIGGER inventory_transaction_no_delete
        BEFORE DELETE ON inventory_transaction
        FOR EACH ROW
        EXECUTE FUNCTION inventory_transaction_refuse_change()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS inventory_transaction_no_update ON inventory_transaction")
    op.execute("DROP TRIGGER IF EXISTS inventory_transaction_no_delete ON inventory_transaction")
    op.execute("DROP INDEX IF EXISTS ix_inventory_transaction_clinic_batch_created")
    op.drop_index(
        op.f("ix_inventory_transaction_clinic_id"),
        table_name="inventory_transaction",
    )
    op.drop_table("inventory_transaction")
    op.execute("DROP FUNCTION IF EXISTS inventory_transaction_refuse_change()")
