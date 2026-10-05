"""One row per role a user holds. A user may hold several."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.roles import ROLES
from dentacircle.models.mixins import ClinicScoped

_ALLOWED = ", ".join(f"'{role}'" for role in ROLES)


class UserRole(ClinicScoped, Base):
    __tablename__ = "user_role"
    __table_args__ = (
        CheckConstraint(f"role IN ({_ALLOWED})", name="role_known"),
        ForeignKeyConstraint(
            ["clinic_id", "user_id"],
            ["app_user.clinic_id", "app_user.id"],
        ),
    )

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
