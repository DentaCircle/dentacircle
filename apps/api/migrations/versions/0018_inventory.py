"""Inventory categories, items and batches.

Revision ID: 0018_inventory
Revises: 0017_lab_work
Create Date: 2026-10-25

Adds three tables. A batch stores a number and an optional expiry date.
It does not store a quantity, a cost or a supplier.

Downgrade drops the three tables. Rows in them are not restored.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_inventory"
down_revision: str | None = "0017_lab_work"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = ("active", "inactive")


def upgrade() -> None:
    op.create_table(
        "inventory_category",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 80",
            name=op.f("ck_inventory_category_name_length"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_inventory_category_clinic_id_clinic"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_category")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_inventory_category_id_clinic_id"),
    )
    op.create_index(op.f("ix_inventory_category_clinic_id"), "inventory_category", ["clinic_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_inventory_category_name"
        " ON inventory_category (clinic_id, lower(name))"
    )

    op.create_table(
        "inventory_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{status}'" for status in _STATUSES) + ")",
            name=op.f("ck_inventory_item_status_known"),
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120",
            name=op.f("ck_inventory_item_name_length"),
        ),
        sa.CheckConstraint(
            "char_length(unit) BETWEEN 1 AND 30",
            name=op.f("ck_inventory_item_unit_length"),
        ),
        sa.CheckConstraint(
            "low_stock_threshold BETWEEN 0 AND 1000000",
            name=op.f("ck_inventory_item_threshold_range"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_inventory_item_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id", "clinic_id"],
            ["inventory_category.id", "inventory_category.clinic_id"],
            name="fk_inventory_item_category_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_item")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_inventory_item_id_clinic_id"),
    )
    op.create_index(op.f("ix_inventory_item_clinic_id"), "inventory_item", ["clinic_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_inventory_item_name ON inventory_item (clinic_id, lower(name))"
    )
    op.execute(
        "CREATE INDEX ix_inventory_item_clinic_status_name"
        " ON inventory_item (clinic_id, status, lower(name))"
    )
    op.create_index(
        "ix_inventory_item_clinic_category",
        "inventory_item",
        ["clinic_id", "category_id"],
    )

    op.create_table(
        "inventory_batch",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("batch_number", sa.Text(), nullable=False),
        sa.Column("expiry_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(batch_number) BETWEEN 1 AND 60",
            name=op.f("ck_inventory_batch_batch_number_length"),
        ),
        sa.CheckConstraint(
            "expiry_on IS NULL OR expiry_on >= DATE '2000-01-01'",
            name=op.f("ck_inventory_batch_expiry_not_before_2000"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_inventory_batch_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "clinic_id"],
            ["inventory_item.id", "inventory_item.clinic_id"],
            name="fk_inventory_batch_item_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_batch")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_inventory_batch_id_clinic_id"),
    )
    op.create_index(op.f("ix_inventory_batch_clinic_id"), "inventory_batch", ["clinic_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_inventory_batch_number"
        " ON inventory_batch (item_id, lower(batch_number))"
    )
    op.create_index(
        "ix_inventory_batch_clinic_item",
        "inventory_batch",
        ["clinic_id", "item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_batch_clinic_item", table_name="inventory_batch")
    op.execute("DROP INDEX uq_inventory_batch_number")
    op.drop_index(op.f("ix_inventory_batch_clinic_id"), table_name="inventory_batch")
    op.drop_table("inventory_batch")
    op.drop_index("ix_inventory_item_clinic_category", table_name="inventory_item")
    op.execute("DROP INDEX ix_inventory_item_clinic_status_name")
    op.execute("DROP INDEX uq_inventory_item_name")
    op.drop_index(op.f("ix_inventory_item_clinic_id"), table_name="inventory_item")
    op.drop_table("inventory_item")
    op.execute("DROP INDEX uq_inventory_category_name")
    op.drop_index(op.f("ix_inventory_category_clinic_id"), table_name="inventory_category")
    op.drop_table("inventory_category")
