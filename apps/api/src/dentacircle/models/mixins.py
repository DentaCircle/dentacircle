"""Shared columns for rows that belong to one clinic."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class ClinicScoped:
    """Adds clinic_id. Every repository query on these rows filters by it."""

    @declared_attr
    @classmethod
    def clinic_id(cls) -> Mapped[UUID]:
        return mapped_column(ForeignKey("clinic.id"), index=True)

    @declared_attr
    @classmethod
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), server_default=func.now())
