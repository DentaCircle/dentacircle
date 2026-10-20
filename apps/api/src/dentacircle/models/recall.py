"""One open recall per patient. Closed rows stay so a later visit can open another."""

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
from dentacircle.domain.recall import OPEN_RECALL_STATUSES, RECALL_STATUSES
from dentacircle.models.mixins import ClinicScoped

_STATUSES = ", ".join(f"'{status}'" for status in RECALL_STATUSES)
_OPEN = ", ".join(f"'{status}'" for status in sorted(OPEN_RECALL_STATUSES))


class Recall(ClinicScoped, Base):
    __tablename__ = "recall"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_recall_id_clinic_id"),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_known"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_recall_patient_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_type.id", "appointment_type.clinic_id"],
            name="fk_recall_appointment_type_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["source_appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_recall_source_appointment_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["booked_appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_recall_booked_appointment_id_clinic_id",
        ),
        Index(
            "uq_recall_open_patient",
            "clinic_id",
            "patient_id",
            unique=True,
            postgresql_where=text(f"status IN ({_OPEN})"),
        ),
        Index("ix_recall_clinic_status_due", "clinic_id", "status", "due_on"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_id: Mapped[UUID] = mapped_column()
    appointment_type_id: Mapped[UUID] = mapped_column()
    source_appointment_id: Mapped[UUID] = mapped_column()
    booked_appointment_id: Mapped[UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        Text, default="scheduled", server_default=text("'scheduled'")
    )
    due_on: Mapped[date] = mapped_column(Date)
