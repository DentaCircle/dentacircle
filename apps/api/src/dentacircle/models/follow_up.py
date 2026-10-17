"""One open follow-up per patient. Closed rows stay so a later visit can open another."""

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
from dentacircle.domain.follow_up import FOLLOW_UP_STATUSES, OPEN_FOLLOW_UP_STATUSES
from dentacircle.models.mixins import ClinicScoped

_STATUSES = ", ".join(f"'{status}'" for status in FOLLOW_UP_STATUSES)
_OPEN = ", ".join(f"'{status}'" for status in sorted(OPEN_FOLLOW_UP_STATUSES))


class FollowUp(ClinicScoped, Base):
    __tablename__ = "follow_up"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_follow_up_id_clinic_id"),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_known"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_follow_up_patient_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_follow_up_appointment_id_clinic_id",
        ),
        Index(
            "uq_follow_up_open_patient",
            "clinic_id",
            "patient_id",
            unique=True,
            postgresql_where=text(f"status IN ({_OPEN})"),
        ),
        Index("ix_follow_up_clinic_status_due", "clinic_id", "status", "due_on"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_id: Mapped[UUID] = mapped_column()
    appointment_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(
        Text, default="scheduled", server_default=text("'scheduled'")
    )
    due_on: Mapped[date] = mapped_column(Date)
