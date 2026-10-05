"""Login, logout and resolving the caller from a session cookie."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from dentacircle.core.security import (
    hash_token,
    new_session_token,
    verify_dummy_password,
    verify_password,
)
from dentacircle.models.app_user import AppUser
from dentacircle.models.auth_session import AuthSession
from dentacircle.models.clinic import Clinic
from dentacircle.repositories.session_repository import (
    SessionRepository,
    delete_by_token_hash,
    find_by_token_hash,
)
from dentacircle.repositories.user_repository import UserRepository, find_for_login


@dataclass(frozen=True)
class ClinicSummary:
    id: UUID
    name: str


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str
    full_name: str
    roles: list[str]
    clinic: ClinicSummary


@dataclass(frozen=True)
class LoginResult:
    user: CurrentUser
    token: str


class InvalidCredentialsError(Exception):
    """Unknown email, wrong password or inactive user. Callers must not tell these apart."""


class UnauthenticatedError(Exception):
    """No usable session."""


def login(session: Session, email: str, password: str, ttl_hours: int) -> LoginResult:
    user = find_for_login(session, email)
    if user is None:
        verify_dummy_password(password)
        raise InvalidCredentialsError
    if not verify_password(user.password_hash, password) or not user.is_active:
        raise InvalidCredentialsError
    return _open_session(session, user, ttl_hours)


def resolve_session(session: Session, token: str) -> CurrentUser:
    auth_session = find_by_token_hash(session, hash_token(token))
    if auth_session is None or auth_session.expires_at <= datetime.now(UTC):
        raise UnauthenticatedError
    repository = UserRepository(session, auth_session.clinic_id)
    user = repository.get(auth_session.user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedError
    return _summary(session, user, repository.roles_for(user.id))


def logout(session: Session, token: str | None) -> None:
    if token is None:
        return
    delete_by_token_hash(session, hash_token(token))


def _open_session(session: Session, user: AppUser, ttl_hours: int) -> LoginResult:
    token = new_session_token()
    SessionRepository(session, user.clinic_id).add(
        AuthSession(
            id=uuid4(),
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
        )
    )
    session.flush()
    repository = UserRepository(session, user.clinic_id)
    return LoginResult(_summary(session, user, repository.roles_for(user.id)), token)


def _summary(session: Session, user: AppUser, roles: list[str]) -> CurrentUser:
    clinic = session.get(Clinic, user.clinic_id)
    if clinic is None:
        raise UnauthenticatedError
    return CurrentUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=roles,
        clinic=ClinicSummary(id=clinic.id, name=clinic.name),
    )
