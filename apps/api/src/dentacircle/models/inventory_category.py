"""A name for a group of stocked items. Renamed, never deleted."""

from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.inventory import MAX_CATEGORY_NAME_LENGTH
from dentacircle.models.mixins import ClinicScoped


class InventoryCategory(ClinicScoped, Base):
    __tablename__ = "inventory_category"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_inventory_category_id_clinic_id"),
        CheckConstraint(
            f"char_length(name) BETWEEN 1 AND {MAX_CATEGORY_NAME_LENGTH}",
            name="name_length",
        ),
        Index("uq_inventory_category_name", "clinic_id", text("lower(name)"), unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
