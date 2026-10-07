"""A label on the calendar. Deactivated, never deleted, so a later visit can still point at it."""

from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.models.mixins import ClinicScoped


class AppointmentType(ClinicScoped, Base):
    __tablename__ = "appointment_type"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_appointment_type_id_clinic_id"),
        CheckConstraint(
            "duration_minutes IS NULL OR (duration_minutes BETWEEN 5 AND 480)",
            name="duration_range",
        ),
        Index("uq_appointment_type_name", "clinic_id", text("lower(name)"), unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
