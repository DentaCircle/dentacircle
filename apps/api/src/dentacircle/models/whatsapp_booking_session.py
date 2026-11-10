"""Persisted state for a single patient booking conversation."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base


class WhatsAppBookingSession(Base):
    __tablename__ = "whatsapp_booking_session"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(ForeignKey("clinic.id"))
    contact_id: Mapped[UUID] = mapped_column()
    account_key: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    menu_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    menu_token: Mapped[str] = mapped_column(Text)
    automation_version: Mapped[int] = mapped_column(Integer)
    choices: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    acknowledged_visits: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    appointment_type_id: Mapped[UUID | None] = mapped_column()
    clinician_user_id: Mapped[UUID | None] = mapped_column()
    selected_date: Mapped[date | None] = mapped_column(Date)
    follow_up_id: Mapped[UUID | None] = mapped_column()
    recall_id: Mapped[UUID | None] = mapped_column()
    booked_appointment_id: Mapped[UUID | None] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
