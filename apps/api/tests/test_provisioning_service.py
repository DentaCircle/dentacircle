from uuid import UUID

import pytest
from alembic import command
from sqlalchemy.orm import Session

from dentacircle.models.clinic import Clinic
from dentacircle.repositories.user_repository import UserRepository, find_for_login
from dentacircle.services.provisioning_service import (
    DuplicateEmailError,
    UnknownRoleError,
    create_user,
    get_or_create_clinic,
)
from tests.test_migrations import _config

_PASSWORD = "synthetic-password-marker"


@pytest.fixture
def migrated(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")


def test_get_or_create_clinic_returns_the_existing_one(migrated: None, db_session: Session) -> None:
    first = get_or_create_clinic(db_session, "Synthetic Clinic")
    second = get_or_create_clinic(db_session, "Synthetic Clinic")
    assert second.id == first.id


def test_create_user_stores_a_lowercase_email_and_a_hash(
    migrated: None, db_session: Session
) -> None:
    clinic = get_or_create_clinic(db_session, "Synthetic Clinic")
    user = create_user(
        db_session, clinic.id, "A@x.test", "Synthetic Person", _PASSWORD, ["clinician"]
    )
    assert user.email == "a@x.test"
    assert user.password_hash != _PASSWORD
    assert _PASSWORD not in user.password_hash
    assert UserRepository(db_session, clinic.id).roles_for(user.id) == ["clinician"]


def test_create_user_rejects_an_unknown_role(migrated: None, db_session: Session) -> None:
    clinic = get_or_create_clinic(db_session, "Synthetic Clinic")
    with pytest.raises(UnknownRoleError):
        create_user(db_session, clinic.id, "a@x.test", "Synthetic Person", _PASSWORD, ["owner"])
    assert find_for_login(db_session, "a@x.test") is None


def test_create_user_rejects_a_duplicate_email_ignoring_case(
    migrated: None, db_session: Session
) -> None:
    clinic = get_or_create_clinic(db_session, "Synthetic Clinic")
    create_user(db_session, clinic.id, "a@x.test", "Synthetic Person", _PASSWORD, ["clinician"])
    with pytest.raises(DuplicateEmailError):
        create_user(
            db_session,
            clinic.id,
            "A@x.test",
            "Synthetic Person",
            _PASSWORD,
            ["receptionist"],
        )


def test_create_user_rejects_a_duplicate_email_in_another_clinic(
    migrated: None, db_session: Session
) -> None:
    first = get_or_create_clinic(db_session, "Synthetic Clinic")
    second_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    db_session.add(Clinic(id=second_id, name="Other Synthetic Clinic"))
    db_session.flush()
    create_user(db_session, first.id, "a@x.test", "Synthetic Person", _PASSWORD, ["clinician"])
    with pytest.raises(DuplicateEmailError):
        create_user(db_session, second_id, "a@x.test", "Synthetic Person", _PASSWORD, ["clinician"])
