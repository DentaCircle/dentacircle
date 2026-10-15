"""A patient's care plan. Open or finished is calculated from its items."""

from uuid import UUID

from sqlalchemy import ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.models.mixins import ClinicScoped


class CarePlan(ClinicScoped, Base):
    __tablename__ = "care_plan"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_care_plan_id_clinic_id"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_care_plan_patient_id_clinic_id",
        ),
        Index("ix_care_plan_clinic_patient_created", "clinic_id", "patient_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_id: Mapped[UUID] = mapped_column()
    title: Mapped[str] = mapped_column(String(200))
