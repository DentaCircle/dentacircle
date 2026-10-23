"""A file attached to a patient. The bytes live in storage, found by `storage_key`."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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
from dentacircle.domain.document import DOCUMENT_CONTENT_TYPES, MAX_DOCUMENT_BYTES

_TYPES = ", ".join(f"'{content_type}'" for content_type in DOCUMENT_CONTENT_TYPES)


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint("char_length(filename) BETWEEN 1 AND 200", name="filename_length"),
        CheckConstraint(f"content_type IN ({_TYPES})", name="content_type_known"),
        CheckConstraint(f"size_bytes BETWEEN 1 AND {MAX_DOCUMENT_BYTES}", name="size_in_range"),
        UniqueConstraint("id", "clinic_id", name="uq_document_id_clinic_id"),
        UniqueConstraint("storage_key", name="uq_document_storage_key"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_document_patient_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["uploaded_by_user_id", "clinic_id"],
            ["app_user.id", "app_user.clinic_id"],
            name="fk_document_uploaded_by_user_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_document_appointment_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["follow_up_id", "clinic_id"],
            ["follow_up.id", "follow_up.clinic_id"],
            name="fk_document_follow_up_id_clinic_id",
        ),
        Index(
            "ix_document_patient_order",
            "clinic_id",
            "patient_id",
            desc("created_at"),
            desc("id"),
        ),
        Index("ix_document_clinic_appointment", "clinic_id", "appointment_id"),
        Index("ix_document_clinic_follow_up", "clinic_id", "follow_up_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(ForeignKey("clinic.id"))
    patient_id: Mapped[UUID] = mapped_column()
    uploaded_by_user_id: Mapped[UUID] = mapped_column()
    filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column()
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column()
    appointment_id: Mapped[UUID | None] = mapped_column()
    follow_up_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
