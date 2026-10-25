"""One stock movement. Insert only.

A database trigger rejects UPDATE and DELETE. Quantity on a batch is the sum
of these rows. This table stores no running total and no item id: the item
is always the batch's item.
"""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.inventory import (
    ADJUSTMENT_REASONS,
    MAX_QUANTITY_CHANGE,
    TRANSACTION_TYPES,
)
from dentacircle.models.mixins import ClinicScoped

_TYPES = ", ".join(f"'{name}'" for name in TRANSACTION_TYPES)
_REASONS = ", ".join(f"'{name}'" for name in ADJUSTMENT_REASONS)
_SIGN = (
    "(type = 'restock' AND quantity_change > 0 AND reason IS NULL) OR "
    "(type = 'adjustment' AND reason IS NOT NULL AND reason IN (" + _REASONS + ") AND "
    "(reason = 'correction' OR quantity_change < 0))"
)


class InventoryTransaction(ClinicScoped, Base):
    __tablename__ = "inventory_transaction"
    __table_args__ = (
        CheckConstraint(f"type IN ({_TYPES})", name="type_known"),
        CheckConstraint(
            "quantity_change <> 0 AND quantity_change BETWEEN "
            f"{-MAX_QUANTITY_CHANGE} AND {MAX_QUANTITY_CHANGE}",
            name="quantity_range",
        ),
        CheckConstraint(_SIGN, name="type_reason_sign"),
        ForeignKeyConstraint(
            ["batch_id", "clinic_id"],
            ["inventory_batch.id", "inventory_batch.clinic_id"],
            name="fk_inventory_transaction_batch_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id", "clinic_id"],
            ["app_user.id", "app_user.clinic_id"],
            name="fk_inventory_transaction_created_by_user_id_clinic_id",
        ),
        Index(
            "ix_inventory_transaction_clinic_batch_created",
            "clinic_id",
            "batch_id",
            text("created_at DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    batch_id: Mapped[UUID] = mapped_column()
    type: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity_change: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[UUID] = mapped_column()
