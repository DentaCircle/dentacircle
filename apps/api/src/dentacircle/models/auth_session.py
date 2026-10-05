"""A login. The cookie holds a random token; this row holds only its hash."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.models.mixins import ClinicScoped


class AuthSession(ClinicScoped, Base):
    __tablename__ = "auth_session"
    __table_args__ = (
        ForeignKeyConstraint(
            ["clinic_id", "user_id"],
            ["app_user.clinic_id", "app_user.id"],
        ),
        Index("ix_auth_session_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID]
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
