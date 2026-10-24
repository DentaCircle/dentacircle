"""One step on a patient's timeline. The row is never updated or deleted."""

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
    Text,
    desc,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.timeline import TIMELINE_KINDS, subject_check_sql

_KINDS = ", ".join(f"'{kind}'" for kind in TIMELINE_KINDS)


class TimelineEvent(Base):
    __tablename__ = "timeline_event"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_KINDS})", name="kind_known"),
        CheckConstraint(subject_check_sql(), name="subject_matches_kind"),
        ForeignKeyConstraint(
            ["clinic_id", "actor_user_id"],
            ["app_user.clinic_id", "app_user.id"],
            name="fk_timeline_event_clinic_id_actor_user_id",
        ),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_timeline_event_patient_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_timeline_event_appointment_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["care_item_id", "clinic_id"],
            ["care_item.id", "care_item.clinic_id"],
            name="fk_timeline_event_care_item_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["care_session_id", "clinic_id"],
            ["care_session.id", "care_session.clinic_id"],
            name="fk_timeline_event_care_session_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["follow_up_id", "clinic_id"],
            ["follow_up.id", "follow_up.clinic_id"],
            name="fk_timeline_event_follow_up_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["recall_id", "clinic_id"],
            ["recall.id", "recall.clinic_id"],
            name="fk_timeline_event_recall_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["document_id", "clinic_id"],
            ["document.id", "document.clinic_id"],
            name="fk_timeline_event_document_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["lab_work_id", "clinic_id"],
            ["lab_work.id", "lab_work.clinic_id"],
            name="fk_timeline_event_lab_work_id_clinic_id",
        ),
        Index(
            "ix_timeline_event_patient_order",
            "clinic_id",
            "patient_id",
            desc("occurred_at"),
            desc("seq"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    clinic_id: Mapped[UUID] = mapped_column(ForeignKey("clinic.id"))
    patient_id: Mapped[UUID] = mapped_column()
    actor_user_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    appointment_id: Mapped[UUID | None] = mapped_column()
    care_item_id: Mapped[UUID | None] = mapped_column()
    care_session_id: Mapped[UUID | None] = mapped_column()
    follow_up_id: Mapped[UUID | None] = mapped_column()
    recall_id: Mapped[UUID | None] = mapped_column()
    document_id: Mapped[UUID | None] = mapped_column()
    lab_work_id: Mapped[UUID | None] = mapped_column()
