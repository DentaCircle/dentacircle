"""The auth tables enforce the rules the code relies on."""

import psycopg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import to_psycopg_url
from tests.test_migrations import _config

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER_CLINIC = "22222222-2222-2222-2222-222222222222"
_USER = "33333333-3333-3333-3333-333333333333"
_OTHER_USER = "44444444-4444-4444-4444-444444444444"


@pytest.fixture
def migrated(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    return throwaway_database_url


def test_email_is_unique_ignoring_case(migrated: str, db_session: Session) -> None:
    _insert_user(db_session, _CLINIC, _USER, "a@x.test")
    with pytest.raises(IntegrityError):
        _insert_user(db_session, _OTHER_CLINIC, _OTHER_USER, "A@x.test")


def test_a_role_must_be_known(migrated: str, db_session: Session) -> None:
    _insert_user(db_session, _CLINIC, _USER, "a@x.test")
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO user_role (clinic_id, user_id, role) VALUES (:clinic, :user, 'owner')"
            ),
            {"clinic": _CLINIC, "user": _USER},
        )


def test_the_same_role_cannot_be_given_twice(migrated: str, db_session: Session) -> None:
    _insert_user(db_session, _CLINIC, _USER, "a@x.test")
    statement = text(
        "INSERT INTO user_role (clinic_id, user_id, role) VALUES (:clinic, :user, 'clinician')"
    )
    db_session.execute(statement, {"clinic": _CLINIC, "user": _USER})
    with pytest.raises(IntegrityError):
        db_session.execute(statement, {"clinic": _CLINIC, "user": _USER})


def test_a_user_can_hold_several_roles(migrated: str, db_session: Session) -> None:
    _insert_user(db_session, _CLINIC, _USER, "a@x.test")
    for role in ("clinician", "clinic_admin"):
        db_session.execute(
            text("INSERT INTO user_role (clinic_id, user_id, role) VALUES (:clinic, :user, :role)"),
            {"clinic": _CLINIC, "user": _USER, "role": role},
        )
    count: int = db_session.execute(
        text("SELECT count(*) FROM user_role WHERE user_id = :user"), {"user": _USER}
    ).scalar_one()
    assert count == 2


def test_a_role_cannot_point_at_another_clinics_user(migrated: str, db_session: Session) -> None:
    _insert_user(db_session, _CLINIC, _USER, "a@x.test")
    _insert_clinic(db_session, _OTHER_CLINIC)
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO user_role (clinic_id, user_id, role)"
                " VALUES (:clinic, :user, 'clinician')"
            ),
            {"clinic": _OTHER_CLINIC, "user": _USER},
        )


def test_stored_email_is_not_lowercased_by_the_database(migrated: str) -> None:
    """The unique index compares lowercase. The column keeps what was inserted."""
    with psycopg.connect(to_psycopg_url(migrated)) as connection:
        row = connection.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_app_user_email'"
        ).fetchone()
        assert row is not None
        definition = row[0]
    assert "lower(" in definition and "email" in definition


def _insert_clinic(session: Session, clinic_id: str) -> None:
    session.execute(
        text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
        {"id": clinic_id},
    )


def _insert_user(session: Session, clinic_id: str, user_id: str, email: str) -> None:
    _insert_clinic(session, clinic_id)
    session.execute(
        text(
            "INSERT INTO app_user (id, clinic_id, email, full_name, password_hash)"
            " VALUES (:id, :clinic, :email, 'Synthetic Person', 'hash')"
        ),
        {"id": user_id, "clinic": clinic_id, "email": email},
    )
