"""Who did what, and when. The row never stores patient values."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.audit import AUDIT_ACTIONS

_ALLOWED = ", ".join(f"'{action}'" for action in AUDIT_ACTIONS)


class AuditEvent(Base):
    __tablename__ = "audit_event"
    __table_args__ = (
        CheckConstraint(f"action IN ({_ALLOWED})", name="action_known"),
        ForeignKeyConstraint(
            ["clinic_id", "actor_user_id"],
            ["app_user.clinic_id", "app_user.id"],
            name="fk_audit_event_clinic_id_app_user",
        ),
        Index(
            "ix_audit_event_entity",
            "clinic_id",
            "entity_type",
            "entity_id",
            "occurred_at",
        ),
        Index("ix_audit_event_occurred", "clinic_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(ForeignKey("clinic.id"))
    actor_user_id: Mapped[UUID] = mapped_column()
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[UUID] = mapped_column()
    action: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
