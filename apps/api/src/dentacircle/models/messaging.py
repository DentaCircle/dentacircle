"""Explicit patient contacts and durable messaging history."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    desc,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base


class MessagingContact(Base):
    __tablename__ = "messaging_contact"
    __table_args__ = (
        ForeignKeyConstraint(["patient_id", "clinic_id"], ["patient.id", "patient.clinic_id"]),
        ForeignKeyConstraint(
            ["created_by_user_id", "clinic_id"], ["app_user.id", "app_user.clinic_id"]
        ),
        UniqueConstraint("clinic_id", "patient_id", name="uq_messaging_contact_patient"),
        UniqueConstraint("clinic_id", "account_key", "number", name="uq_messaging_contact_number"),
        UniqueConstraint("id", "clinic_id", "account_key", name="uq_messaging_contact_account"),
        CheckConstraint("number ~ '^[+][1-9][0-9]{1,14}$'", name="number_e164"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(ForeignKey("clinic.id"))
    patient_id: Mapped[UUID] = mapped_column()
    account_key: Mapped[str] = mapped_column(Text)
    number: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        ForeignKeyConstraint(
            ["contact_id", "clinic_id", "account_key"],
            [
                "messaging_contact.id",
                "messaging_contact.clinic_id",
                "messaging_contact.account_key",
            ],
        ),
        ForeignKeyConstraint(
            ["created_by_user_id", "clinic_id"], ["app_user.id", "app_user.clinic_id"]
        ),
        UniqueConstraint("clinic_id", "request_id", name="uq_message_request"),
        UniqueConstraint(
            "clinic_id", "account_key", "provider_message_id", name="uq_message_provider_id"
        ),
        CheckConstraint("char_length(body) BETWEEN 1 AND 2000", name="body_length"),
        CheckConstraint(
            "(direction = 'inbound' AND state = 'received' AND created_by_user_id IS NULL "
            "AND request_id IS NULL AND provider_message_id IS NOT NULL) OR "
            "(direction = 'outbound' AND state IN ('sending', 'accepted', 'failed', 'unknown') "
            "AND created_by_user_id IS NOT NULL AND request_id IS NOT NULL)",
            name="direction_state_actor",
        ),
        Index(
            "ix_message_contact_order", "clinic_id", "contact_id", desc("created_at"), desc("id")
        ),
        Index("ix_message_clinic_order", "clinic_id", desc("created_at"), desc("id")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(ForeignKey("clinic.id"))
    contact_id: Mapped[UUID] = mapped_column()
    account_key: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[UUID | None] = mapped_column()
    request_id: Mapped[UUID | None] = mapped_column()
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    provider_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
