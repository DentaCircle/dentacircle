"""Procedure resource rules, and consumption on an inventory transaction.

Revision ID: 0020_procedure_resource_rules
Revises: 0019_inventory_transactions
Create Date: 2026-10-26

Adds procedure_resource_rule. Adds a nullable appointment_id on
inventory_transaction and recreates the type and sign checks so a
consumption row can point at the visit. Existing restock and adjustment
rows stay valid: their appointment_id is null.

Downgrade removes consumption rows (the append-only trigger is paused
for that delete only), drops the column and the rule table, and puts
the previous checks back. Restock and adjustment rows are kept.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_procedure_resource_rules"
down_revision: str | None = "0019_inventory_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_TYPES = ("restock", "adjustment")
_NEW_TYPES = ("restock", "adjustment", "consumption")
_REASONS = ("damaged", "expired", "correction")
_OLD_SIGN = (
    "(type = 'restock' AND quantity_change > 0 AND reason IS NULL) OR "
    "(type = 'adjustment' AND reason IS NOT NULL AND reason IN ("
    + ", ".join(f"'{reason}'" for reason in _REASONS)
    + ") AND (reason = 'correction' OR quantity_change < 0))"
)
_NEW_SIGN = (
    "(type = 'restock' AND quantity_change > 0 AND reason IS NULL"
    " AND appointment_id IS NULL) OR "
    "(type = 'adjustment' AND reason IS NOT NULL AND reason IN ("
    + ", ".join(f"'{reason}'" for reason in _REASONS)
    + ") AND (reason = 'correction' OR quantity_change < 0)"
    " AND appointment_id IS NULL) OR "
    "(type = 'consumption' AND quantity_change < 0 AND reason IS NULL"
    " AND appointment_id IS NOT NULL)"
)


def upgrade() -> None:
    op.create_table(
        "procedure_resource_rule",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_type_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 1000",
            name=op.f("ck_procedure_resource_rule_quantity_range"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_procedure_resource_rule_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_type.id", "appointment_type.clinic_id"],
            name="fk_procedure_resource_rule_appointment_type_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "clinic_id"],
            ["inventory_item.id", "inventory_item.clinic_id"],
            name="fk_procedure_resource_rule_item_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_procedure_resource_rule")),
        sa.UniqueConstraint(
            "clinic_id",
            "appointment_type_id",
            "item_id",
            name="uq_procedure_resource_rule_type_item",
        ),
    )
    op.create_index(
        op.f("ix_procedure_resource_rule_clinic_id"),
        "procedure_resource_rule",
        ["clinic_id"],
    )
    op.add_column(
        "inventory_transaction",
        sa.Column("appointment_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventory_transaction_appointment_id_clinic_id",
        "inventory_transaction",
        "appointment",
        ["appointment_id", "clinic_id"],
        ["id", "clinic_id"],
    )
    op.drop_constraint(
        op.f("ck_inventory_transaction_type_reason_sign"),
        "inventory_transaction",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_inventory_transaction_type_known"),
        "inventory_transaction",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_inventory_transaction_type_known"),
        "inventory_transaction",
        "type IN (" + ", ".join(f"'{name}'" for name in _NEW_TYPES) + ")",
    )
    op.create_check_constraint(
        op.f("ck_inventory_transaction_type_reason_sign"),
        "inventory_transaction",
        _NEW_SIGN,
    )


def downgrade() -> None:
    op.execute("ALTER TABLE inventory_transaction DISABLE TRIGGER inventory_transaction_no_delete")
    op.execute("DELETE FROM inventory_transaction WHERE type = 'consumption'")
    op.execute("ALTER TABLE inventory_transaction ENABLE TRIGGER inventory_transaction_no_delete")
    op.drop_constraint(
        op.f("ck_inventory_transaction_type_reason_sign"),
        "inventory_transaction",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_inventory_transaction_type_known"),
        "inventory_transaction",
        type_="check",
    )
    op.drop_constraint(
        "fk_inventory_transaction_appointment_id_clinic_id",
        "inventory_transaction",
        type_="foreignkey",
    )
    op.drop_column("inventory_transaction", "appointment_id")
    op.create_check_constraint(
        op.f("ck_inventory_transaction_type_known"),
        "inventory_transaction",
        "type IN (" + ", ".join(f"'{name}'" for name in _OLD_TYPES) + ")",
    )
    op.create_check_constraint(
        op.f("ck_inventory_transaction_type_reason_sign"),
        "inventory_transaction",
        _OLD_SIGN,
    )
    op.drop_index(
        op.f("ix_procedure_resource_rule_clinic_id"),
        table_name="procedure_resource_rule",
    )
    op.drop_table("procedure_resource_rule")
