"""One service on a care plan. Status moves only through the allowed pairs."""

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.care import CARE_ITEM_STATUSES
from dentacircle.models.mixins import ClinicScoped

_STATUSES = ", ".join(f"'{status}'" for status in CARE_ITEM_STATUSES)


class CareItem(ClinicScoped, Base):
    __tablename__ = "care_item"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_care_item_id_clinic_id"),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_known"),
        ForeignKeyConstraint(
            ["care_plan_id", "clinic_id"],
            ["care_plan.id", "care_plan.clinic_id"],
            name="fk_care_item_care_plan_id_clinic_id",
        ),
        Index("ix_care_item_clinic_plan_created", "clinic_id", "care_plan_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    care_plan_id: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(Text, default="planned", server_default=text("'planned'"))
