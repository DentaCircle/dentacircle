from datetime import time
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy.orm import Session

from dentacircle.domain.clinic_day import DEFAULT_APPOINTMENT_TYPES, DEFAULT_WORKING_HOURS
from dentacircle.models.clinic import Clinic
from dentacircle.repositories.appointment_type_repository import AppointmentTypeRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
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


def test_a_new_clinic_is_seeded_and_an_existing_one_is_left_alone(
    migrated: None, db_session: Session
) -> None:
    clinic = get_or_create_clinic(db_session, "Synthetic Clinic")
    hours = ClinicDayRepository(db_session, clinic.id)
    types = AppointmentTypeRepository(db_session, clinic.id)
    assert [(row.weekday, row.opens_at, row.closes_at) for row in hours.list_hours()] == [
        (item.weekday, item.opens_at, item.closes_at) for item in DEFAULT_WORKING_HOURS
    ]
    expected_types = sorted(DEFAULT_APPOINTMENT_TYPES, key=lambda item: item.name.lower())
    assert [(row.name, row.duration_minutes, row.is_active) for row in types.list_types(True)] == [
        (item.name, item.duration_minutes, True) for item in expected_types
    ]

    hours.replace_hours([(0, time(10, 0), time(14, 0))])
    db_session.flush()
    again = get_or_create_clinic(db_session, "Synthetic Clinic")
    assert again.id == clinic.id
    assert [(row.weekday, row.opens_at, row.closes_at) for row in hours.list_hours()] == [
        (0, time(10, 0), time(14, 0))
    ]
    assert len(types.list_types(True)) == len(DEFAULT_APPOINTMENT_TYPES)
