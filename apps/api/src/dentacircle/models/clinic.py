"""The tenant root. A clinic owns every other clinic-scoped row."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.clinic_day import DEFAULT_APPOINTMENT_MINUTES, DEFAULT_TIMEZONE


class Clinic(Base):
    __tablename__ = "clinic"
    __table_args__ = (
        CheckConstraint(
            "default_appointment_minutes BETWEEN 5 AND 480",
            name="default_appointment_minutes_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(
        Text, default=DEFAULT_TIMEZONE, server_default=f"'{DEFAULT_TIMEZONE}'"
    )
    default_appointment_minutes: Mapped[int] = mapped_column(
        Integer,
        default=DEFAULT_APPOINTMENT_MINUTES,
        server_default=str(DEFAULT_APPOINTMENT_MINUTES),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
