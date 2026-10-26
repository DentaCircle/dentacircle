"""How many units of one item an appointment type uses when the visit is completed."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.inventory import MAX_RULE_QUANTITY
from dentacircle.models.mixins import ClinicScoped


class ProcedureResourceRule(ClinicScoped, Base):
    __tablename__ = "procedure_resource_rule"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "appointment_type_id",
            "item_id",
            name="uq_procedure_resource_rule_type_item",
        ),
        CheckConstraint(
            f"quantity BETWEEN 1 AND {MAX_RULE_QUANTITY}",
            name="quantity_range",
        ),
        ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_type.id", "appointment_type.clinic_id"],
            name="fk_procedure_resource_rule_appointment_type_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["item_id", "clinic_id"],
            ["inventory_item.id", "inventory_item.clinic_id"],
            name="fk_procedure_resource_rule_item_id_clinic_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    appointment_type_id: Mapped[UUID] = mapped_column()
    item_id: Mapped[UUID] = mapped_column()
    quantity: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
