"""One row per clinic. The next patient number is last_number + 1, under a row lock."""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base


class PatientNumberCounter(Base):
    __tablename__ = "patient_number_counter"

    clinic_id: Mapped[UUID] = mapped_column(ForeignKey("clinic.id"), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer)
