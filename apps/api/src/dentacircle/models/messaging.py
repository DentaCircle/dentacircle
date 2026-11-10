"""Explicit patient contacts and durable messaging history."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    desc,
    func,
    text,
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
    automation_state: Mapped[str] = mapped_column(Text, server_default=text("'active'"))
    automation_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    automation_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
        UniqueConstraint("id", "clinic_id", name="uq_message_id_clinic"),
        UniqueConstraint("clinic_id", "caused_by_message_id", name="uq_message_cause"),
        ForeignKeyConstraint(
            ["caused_by_message_id", "clinic_id"],
            ["message.id", "message.clinic_id"],
            name="fk_message_cause",
        ),
        UniqueConstraint("clinic_id", "request_id", name="uq_message_request"),
        UniqueConstraint(
            "clinic_id", "account_key", "provider_message_id", name="uq_message_provider_id"
        ),
        CheckConstraint("char_length(body) BETWEEN 1 AND 2000", name="body_length"),
        CheckConstraint(
            "(origin = 'provider' AND direction = 'inbound' AND state = 'received' "
            "AND created_by_user_id IS NULL AND request_id IS NULL "
            "AND provider_message_id IS NOT NULL AND caused_by_message_id IS NULL) OR "
            "(origin = 'staff' AND direction = 'outbound' "
            "AND state IN ('sending', 'accepted', 'failed', 'unknown') "
            "AND created_by_user_id IS NOT NULL AND request_id IS NOT NULL "
            "AND caused_by_message_id IS NULL) OR "
            "(origin = 'automation' AND direction = 'outbound' "
            "AND state IN ('queued', 'sending', 'accepted', 'failed', 'unknown', 'superseded') "
            "AND created_by_user_id IS NULL AND request_id IS NULL "
            "AND caused_by_message_id IS NOT NULL)",
            name="direction_state_actor",
        ),
        CheckConstraint(
            "(origin = 'automation' AND state = 'sending' "
            "AND dispatch_owner IS NOT NULL AND dispatch_deadline_at IS NOT NULL) OR "
            "((origin != 'automation' OR state != 'sending') AND dispatch_owner IS NULL "
            "AND dispatch_deadline_at IS NULL)",
            name="dispatch_claim",
        ),
        Index("ix_message_dispatch_order", "clinic_id", "contact_id", "dispatch_order"),
        Index(
            "ix_message_dispatch_claim",
            "clinic_id",
            "contact_id",
            "dispatch_deadline_at",
            postgresql_where="state = 'sending' AND dispatch_owner IS NOT NULL",
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
    origin: Mapped[str] = mapped_column(Text)
    caused_by_message_id: Mapped[UUID | None] = mapped_column()
    dispatch_order: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    dispatch_owner: Mapped[UUID | None] = mapped_column()
    dispatch_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purpose: Mapped[str | None] = mapped_column(Text)
    booking_session_id: Mapped[UUID | None] = mapped_column()
    menu_version: Mapped[int | None] = mapped_column(Integer)
    automation_version: Mapped[int | None] = mapped_column(Integer)
    reply_kind: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[UUID | None] = mapped_column()
    request_id: Mapped[UUID | None] = mapped_column()
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    provider_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
