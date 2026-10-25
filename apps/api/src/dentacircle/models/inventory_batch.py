"""A batch label and an optional expiry date. Quantity is the sum of transactions."""

from datetime import date
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.inventory import EARLIEST_EXPIRY, MAX_BATCH_NUMBER_LENGTH
from dentacircle.models.mixins import ClinicScoped


class InventoryBatch(ClinicScoped, Base):
    __tablename__ = "inventory_batch"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_inventory_batch_id_clinic_id"),
        CheckConstraint(
            f"char_length(batch_number) BETWEEN 1 AND {MAX_BATCH_NUMBER_LENGTH}",
            name="batch_number_length",
        ),
        CheckConstraint(
            f"expiry_on IS NULL OR expiry_on >= DATE '{EARLIEST_EXPIRY.isoformat()}'",
            name="expiry_not_before_2000",
        ),
        ForeignKeyConstraint(
            ["item_id", "clinic_id"],
            ["inventory_item.id", "inventory_item.clinic_id"],
            name="fk_inventory_batch_item_id_clinic_id",
        ),
        Index("uq_inventory_batch_number", "item_id", text("lower(batch_number)"), unique=True),
        Index("ix_inventory_batch_clinic_item", "clinic_id", "item_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    item_id: Mapped[UUID] = mapped_column()
    batch_number: Mapped[str] = mapped_column(Text)
    expiry_on: Mapped[date | None] = mapped_column(Date, nullable=True)
