"""One piece of external lab work for a patient. Status moves only through the allowed pairs."""

from datetime import date
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.lab_work import LAB_WORK_STATUSES, MAX_TITLE_LENGTH
from dentacircle.models.mixins import ClinicScoped

_STATUSES = ", ".join(f"'{status}'" for status in LAB_WORK_STATUSES)


class LabWork(ClinicScoped, Base):
    __tablename__ = "lab_work"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_lab_work_id_clinic_id"),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_known"),
        CheckConstraint(
            f"char_length(title) BETWEEN 1 AND {MAX_TITLE_LENGTH}",
            name="title_length",
        ),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_lab_work_patient_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_lab_work_appointment_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id", "clinic_id"],
            ["app_user.id", "app_user.clinic_id"],
            name="fk_lab_work_created_by_user_id_clinic_id",
        ),
        Index(
            "ix_lab_work_patient_order",
            "clinic_id",
            "patient_id",
            desc("created_at"),
            desc("id"),
        ),
        Index("ix_lab_work_clinic_status_expected", "clinic_id", "status", "expected_on"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_id: Mapped[UUID] = mapped_column()
    appointment_id: Mapped[UUID | None] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(Text)
    expected_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending", server_default=text("'pending'"))
    created_by_user_id: Mapped[UUID] = mapped_column()
