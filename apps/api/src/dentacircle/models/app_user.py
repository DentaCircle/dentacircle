"""A person who can log in. Named app_user because user is reserved in PostgreSQL."""

from uuid import UUID

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.models.mixins import ClinicScoped


class AppUser(ClinicScoped, Base):
    __tablename__ = "app_user"
    # Lets user_role and auth_session reference (clinic_id, id), so a child row
    # cannot point at a user in a different clinic.
    __table_args__ = (UniqueConstraint("id", "clinic_id", name="uq_app_user_id_clinic_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
