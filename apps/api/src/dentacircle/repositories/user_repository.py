"""Reads and writes for users. Every method takes a clinic id except the login lookup."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.app_user import AppUser
from dentacircle.models.user_role import UserRole


class UserRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, user: AppUser, roles: list[str]) -> None:
        user.clinic_id = self._clinic_id
        self._session.add(user)
        for role in roles:
            self._session.add(UserRole(clinic_id=self._clinic_id, user_id=user.id, role=role))

    def list_users(self) -> list[AppUser]:
        statement = scoped_select(AppUser, self._clinic_id).order_by(AppUser.email)
        return list(self._session.scalars(statement))

    def get(self, user_id: UUID) -> AppUser | None:
        statement = scoped_select(AppUser, self._clinic_id).where(AppUser.id == user_id)
        return self._session.scalars(statement).one_or_none()

    def roles_for(self, user_id: UUID) -> list[str]:
        statement = (
            scoped_select(UserRole, self._clinic_id)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.role)
        )
        return [row.role for row in self._session.scalars(statement)]


def find_for_login(session: Session, email: str) -> AppUser | None:
    """The one query that is not scoped by clinic. The clinic is not known before login.

    Email is unique across all clinics, so this matches at most one user.
    """
    statement = select(AppUser).where(func.lower(AppUser.email) == email.strip().lower())
    return session.scalars(statement).one_or_none()
