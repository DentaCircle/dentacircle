"""A clinic only ever sees its own users."""

from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy.orm import Session

from dentacircle.models.app_user import AppUser
from dentacircle.models.clinic import Clinic
from dentacircle.repositories.user_repository import UserRepository
from tests.test_migrations import _config

_CLINIC_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_CLINIC_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def migrated(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")


def test_a_clinic_lists_only_its_own_users(migrated: None, db_session: Session) -> None:
    _clinic(db_session, _CLINIC_A, "Synthetic Clinic A")
    _clinic(db_session, _CLINIC_B, "Synthetic Clinic B")
    user_a = _user(db_session, _CLINIC_A, "a@x.test")
    user_b = _user(db_session, _CLINIC_B, "b@x.test")

    listed = UserRepository(db_session, _CLINIC_A).list_users()
    assert [user.email for user in listed] == ["a@x.test"]

    repository = UserRepository(db_session, _CLINIC_A)
    assert repository.get(user_a) is not None
    assert repository.get(user_b) is None


def test_roles_are_read_inside_the_clinic(migrated: None, db_session: Session) -> None:
    _clinic(db_session, _CLINIC_A, "Synthetic Clinic A")
    user_a = _user(db_session, _CLINIC_A, "a@x.test", ["clinician", "receptionist"])

    assert UserRepository(db_session, _CLINIC_A).roles_for(user_a) == [
        "clinician",
        "receptionist",
    ]
    assert UserRepository(db_session, _CLINIC_B).roles_for(user_a) == []


def _clinic(session: Session, clinic_id: UUID, name: str) -> None:
    session.add(Clinic(id=clinic_id, name=name))
    session.flush()


def _user(session: Session, clinic_id: UUID, email: str, roles: list[str] | None = None) -> UUID:
    user_id = uuid4()
    UserRepository(session, clinic_id).add(
        AppUser(
            id=user_id,
            email=email,
            full_name="Synthetic Person",
            password_hash="hash",
            is_active=True,
        ),
        roles or ["clinician"],
    )
    session.flush()
    return user_id
