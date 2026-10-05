"""Reads and writes for login sessions.

find_by_token_hash and delete_by_token_hash are not scoped by clinic: the cookie carries
no clinic id. The token hash is unique, so each matches at most one row, and that row
carries the clinic every later query uses.
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from dentacircle.models.auth_session import AuthSession


class SessionRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, auth_session: AuthSession) -> None:
        auth_session.clinic_id = self._clinic_id
        self._session.add(auth_session)


def find_by_token_hash(session: Session, token_hash: str) -> AuthSession | None:
    statement = select(AuthSession).where(AuthSession.token_hash == token_hash)
    return session.scalars(statement).one_or_none()


def delete_by_token_hash(session: Session, token_hash: str) -> None:
    session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash))
