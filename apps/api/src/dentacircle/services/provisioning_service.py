"""Creates clinics and users. Used by the create-user command, not by a route."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.security import hash_password
from dentacircle.domain.roles import ROLES
from dentacircle.models.app_user import AppUser
from dentacircle.models.clinic import Clinic
from dentacircle.repositories.user_repository import UserRepository


class UnknownRoleError(Exception):
    """A role outside the four the product defines."""


class DuplicateEmailError(Exception):
    """An account with this email already exists, in any clinic."""


def get_or_create_clinic(session: Session, name: str) -> Clinic:
    existing = session.scalars(select(Clinic).where(Clinic.name == name)).one_or_none()
    if existing is not None:
        return existing
    clinic = Clinic(id=uuid4(), name=name)
    session.add(clinic)
    session.flush()
    return clinic


def create_user(
    session: Session,
    clinic_id: UUID,
    email: str,
    full_name: str,
    password: str,
    roles: list[str],
) -> AppUser:
    unknown = [role for role in roles if role not in ROLES]
    if unknown:
        raise UnknownRoleError(unknown[0])
    if not roles:
        raise UnknownRoleError("")
    normalized = email.strip().lower()
    user = AppUser(
        id=uuid4(),
        email=normalized,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        is_active=True,
    )
    UserRepository(session, clinic_id).add(user, sorted(set(roles)))
    try:
        session.flush()
    except IntegrityError:
        raise DuplicateEmailError from None
    return user
