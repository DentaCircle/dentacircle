"""A person registered at one clinic. The number is stable and never reused."""

from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.models.mixins import ClinicScoped


class Patient(ClinicScoped, Base):
    __tablename__ = "patient"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_patient_id_clinic_id"),
        UniqueConstraint("clinic_id", "patient_number", name="uq_patient_clinic_id_patient_number"),
        CheckConstraint(
            "char_length(phone_digits) BETWEEN 7 AND 15",
            name="phone_digits_length",
        ),
        Index("ix_patient_clinic_lower_full_name", "clinic_id", text("lower(full_name)")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_number: Mapped[int] = mapped_column(Integer)
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(30))
    phone_digits: Mapped[str] = mapped_column(String(15))
    date_of_birth: Mapped[date | None] = mapped_column()
