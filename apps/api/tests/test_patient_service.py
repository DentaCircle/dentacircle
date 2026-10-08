"""Patient numbers, validation, and concurrent registration."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine, to_sqlalchemy_url
from dentacircle.domain.patient import (
    PatientFieldError,
    check_date_of_birth,
    clean_name,
    clean_phone,
    display_id,
)
from dentacircle.models.patient import Patient
from dentacircle.services.patient_service import list_patients, register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_PHONE = "9000000001"
_TODAY = date(2026, 10, 8)


def test_display_id_pads_to_four_digits() -> None:
    assert display_id(1) == "P-0001"
    assert display_id(12) == "P-0012"
    assert display_id(10000) == "P-10000"


def test_clean_name_trims_and_rejects_blank_or_long() -> None:
    assert clean_name("  Ada  ") == "Ada"
    with pytest.raises(PatientFieldError) as blank:
        clean_name("   ")
    assert blank.value.field == "full_name"
    assert blank.value.code == "string_too_short"
    with pytest.raises(PatientFieldError) as long:
        clean_name("A" * 201)
    assert long.value.code == "string_too_long"


def test_clean_phone_keeps_the_entered_form_and_the_digits() -> None:
    assert clean_phone("  +91 98765-43210 ") == ("+91 98765-43210", "919876543210")
    assert clean_phone("(98765) 43210") == ("(98765) 43210", "9876543210")


@pytest.mark.parametrize(
    "phone",
    ["", "   ", "123456", "1" * 16, "abcdefg", "12+3456789", "+" + "1" * 16],
)
def test_clean_phone_rejects_a_bad_number(phone: str) -> None:
    with pytest.raises(PatientFieldError) as exc:
        clean_phone(phone)
    assert exc.value.field == "phone"
    assert exc.value.code in {"string_too_short", "string_too_long", "phone_digits"}


def test_date_of_birth_allows_1900_through_today() -> None:
    check_date_of_birth(None, _TODAY)
    check_date_of_birth(date(1900, 1, 1), _TODAY)
    check_date_of_birth(_TODAY, _TODAY)
    with pytest.raises(PatientFieldError) as early:
        check_date_of_birth(date(1899, 12, 31), _TODAY)
    assert early.value.field == "date_of_birth"
    assert early.value.code == "date_before_min"
    with pytest.raises(PatientFieldError) as future:
        check_date_of_birth(_TODAY + timedelta(days=1), _TODAY)
    assert future.value.code == "date_future"


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_numbers_start_at_one_and_each_clinic_has_its_own(database: str) -> None:
    engine = get_engine()
    with Session(engine) as session:
        first = get_or_create_clinic(session, "Synthetic Clinic")
        second = get_or_create_clinic(session, "Other Synthetic Clinic")
        actor = create_user(
            session,
            first.id,
            "a@x.test",
            "Synthetic Person",
            "synthetic-password-marker",
            ["receptionist"],
        )
        other = create_user(
            session,
            second.id,
            "b@x.test",
            "Synthetic Person",
            "synthetic-password-marker",
            ["receptionist"],
        )
        session.commit()
        first_id, second_id = first.id, second.id
        actor_id, other_id = actor.id, other.id

    with Session(engine) as session:
        created = register_patient(session, first_id, actor_id, "Sample Ada", _PHONE, None)
        again = register_patient(
            session, first_id, actor_id, "Sample Ada", _PHONE, date(1990, 4, 5)
        )
        other_patient = register_patient(session, second_id, other_id, "Sample Bea", _PHONE, None)
        session.commit()

    assert created.patient_number == 1
    assert created.display_id == "P-0001"
    assert created.full_name == "Sample Ada"
    assert created.phone == _PHONE
    assert again.patient_number == 2
    assert again.display_id == "P-0002"
    assert again.date_of_birth == date(1990, 4, 5)
    assert other_patient.patient_number == 1
    assert other_patient.display_id == "P-0001"

    with Session(engine) as session:
        page = list_patients(session, first_id, None, 1, 20)
        assert page.total == 2
        assert [item.display_id for item in page.items] == ["P-0001", "P-0002"]
        other_page = list_patients(session, second_id, "P-0001", 1, 20)
        assert [item.id for item in other_page.items] == [other_patient.id]


def test_a_failed_create_does_not_consume_a_number(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            register_patient(session, clinic_id, uuid4(), "Sample Ada", _PHONE, None)
    with Session(get_engine()) as session:
        created = register_patient(session, clinic_id, actor_id, "Sample Bea", _PHONE, None)
        session.commit()
    assert created.patient_number == 1
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Patient)) == 1


def test_two_creates_at_once_get_different_numbers(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    engine = create_engine(
        to_sqlalchemy_url(database),
        pool_size=8,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )

    def create_one(_index: int) -> int:
        with Session(engine) as session:
            created = register_patient(session, clinic_id, actor_id, "Sample Ada", _PHONE, None)
            session.commit()
            return created.patient_number

    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers = list(pool.map(create_one, range(8)))
    engine.dispose()
    assert sorted(numbers) == list(range(1, 9))


def _clinic_and_actor() -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "a@x.test",
            "Synthetic Person",
            "synthetic-password-marker",
            ["receptionist"],
        )
        session.commit()
        return clinic.id, actor.id
