"""A clinic only ever sees its own users, hours and appointment types."""

from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.main import create_app
from dentacircle.models.app_user import AppUser
from dentacircle.models.clinic import Clinic
from dentacircle.repositories.appointment_type_repository import AppointmentTypeRepository
from dentacircle.repositories.user_repository import UserRepository
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
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


def test_an_admin_cannot_read_or_change_another_clinics_day_or_types(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    command.upgrade(_config(), "head")
    clear_engine()
    with Session(get_engine()) as session:
        clinic_a = get_or_create_clinic(session, "Synthetic Clinic A")
        clinic_b = get_or_create_clinic(session, "Synthetic Clinic B")
        create_user(
            session,
            clinic_a.id,
            "admin-a@x.test",
            "Synthetic Admin",
            "synthetic-password-marker",
            ["clinic_admin"],
        )
        create_user(
            session,
            clinic_b.id,
            "admin-b@x.test",
            "Synthetic Admin",
            "synthetic-password-marker",
            ["clinic_admin"],
        )
        session.commit()
        type_b = AppointmentTypeRepository(session, clinic_b.id).list_types(True)[0].id

    with TestClient(create_app()) as client:
        cookie_a = {
            "dc_session": _login(client, "admin-a@x.test"),
        }
        cookie_b = {
            "dc_session": _login(client, "admin-b@x.test"),
        }
        changed = client.put(
            "/clinic/day",
            cookies=cookie_a,
            json={
                "timezone": "Asia/Dubai",
                "default_appointment_minutes": 20,
                "working_hours": [],
            },
        )
        assert changed.status_code == 200
        assert client.get("/clinic/day", cookies=cookie_a).json()["timezone"] == "Asia/Dubai"
        other = client.get("/clinic/day", cookies=cookie_b).json()
        assert other["timezone"] == "Asia/Kolkata"
        assert len(other["working_hours"]) == 6

        ids_a = {row["id"] for row in client.get("/appointment-types", cookies=cookie_a).json()}
        assert str(type_b) not in ids_a
        missing = client.put(
            f"/appointment-types/{type_b}",
            cookies=cookie_a,
            json={"name": "Taken", "duration_minutes": 30, "is_active": True},
        )
        assert missing.status_code == 404
        ids_b = {row["id"] for row in client.get("/appointment-types", cookies=cookie_b).json()}
        assert str(type_b) in ids_b


def _login(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "synthetic-password-marker"},
    )
    assert response.status_code == 200
    return str(response.cookies["dc_session"])


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
