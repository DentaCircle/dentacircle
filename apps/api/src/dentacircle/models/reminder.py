"""A staff-scheduled reminder for an appointment."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.models.mixins import ClinicScoped


class Reminder(ClinicScoped, Base):
    __tablename__ = "reminder"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed', 'cancelled')", name="status_known"),
        ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_reminder_appointment_clinic",
        ),
        Index(
            "uq_reminder_pending_appointment",
            "clinic_id",
            "appointment_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_reminder_pending_due",
            "clinic_id",
            "due_at",
            "id",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    appointment_id: Mapped[UUID] = mapped_column()
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending", server_default=text("'pending'"))
