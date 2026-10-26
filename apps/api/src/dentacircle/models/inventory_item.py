"""Something the clinic stocks. Deactivated, never deleted. Stock is calculated."""

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.inventory import (
    ITEM_STATUSES,
    MAX_ITEM_NAME_LENGTH,
    MAX_LOW_STOCK_THRESHOLD,
    MAX_UNIT_LENGTH,
)
from dentacircle.models.mixins import ClinicScoped

_STATUSES = ", ".join(f"'{status}'" for status in ITEM_STATUSES)


class InventoryItem(ClinicScoped, Base):
    __tablename__ = "inventory_item"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_inventory_item_id_clinic_id"),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_known"),
        CheckConstraint(
            f"char_length(name) BETWEEN 1 AND {MAX_ITEM_NAME_LENGTH}",
            name="name_length",
        ),
        CheckConstraint(
            f"char_length(unit) BETWEEN 1 AND {MAX_UNIT_LENGTH}",
            name="unit_length",
        ),
        CheckConstraint(
            f"low_stock_threshold BETWEEN 0 AND {MAX_LOW_STOCK_THRESHOLD}",
            name="threshold_range",
        ),
        ForeignKeyConstraint(
            ["category_id", "clinic_id"],
            ["inventory_category.id", "inventory_category.clinic_id"],
            name="fk_inventory_item_category_id_clinic_id",
        ),
        Index("uq_inventory_item_name", "clinic_id", text("lower(name)"), unique=True),
        Index("ix_inventory_item_clinic_status_name", "clinic_id", "status", text("lower(name)")),
        Index("ix_inventory_item_clinic_category", "clinic_id", "category_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    category_id: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(Text, default="active", server_default=text("'active'"))
