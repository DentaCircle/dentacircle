"""Booking rules: who can be booked, which starts are real, and who is already busy."""

from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.appointment import AppointmentFieldError
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.services.appointment_service import (
    PatientBusyError,
    SlotTakenError,
    book_appointment,
    find_availability,
    list_clinicians,
    list_upcoming,
)
from dentacircle.services.appointment_type_service import create_appointment_type
from dentacircle.services.patient_service import (
    PatientNotFoundError,
    register_patient,
    set_patient_status,
)
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 12, 8, 0, tzinfo=_ZONE)
_PHONE = "9000000001"


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_clinicians_are_the_active_ones_in_this_clinic_sorted_by_name(database: str) -> None:
    clinic_id, _actor_id, _clinician_id, _patient_id, _type_id = _world()
    with Session(get_engine()) as session:
        create_user(
            session,
            clinic_id,
            "zed@x.test",
            "Zed Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        inactive = create_user(
            session,
            clinic_id,
            "idle@x.test",
            "Ada Idle",
            "synthetic-password-marker",
            ["clinician"],
        )
        inactive.is_active = False
        create_user(
            session,
            clinic_id,
            "desk2@x.test",
            "Ada Desk",
            "synthetic-password-marker",
            ["receptionist"],
        )
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        create_user(
            session,
            other.id,
            "other-clinician@x.test",
            "Aaron Other",
            "synthetic-password-marker",
            ["clinician"],
        )
        session.commit()
    with Session(get_engine()) as session:
        names = [row.full_name for row in list_clinicians(session, clinic_id)]
    assert names == ["Sample Clinician", "Zed Person"]


def test_availability_uses_the_type_duration_or_the_clinic_default(database: str) -> None:
    clinic_id, _actor, clinician_id, _patient, type_id = _world()
    with Session(get_engine()) as session:
        blank = create_appointment_type(session, clinic_id, "Review", None)
        session.commit()
        blank_id = blank.id
    with Session(get_engine()) as session:
        typed = find_availability(session, clinic_id, clinician_id, type_id, _day(1), _NOW)
        defaulted = find_availability(session, clinic_id, clinician_id, blank_id, _day(1), _NOW)
    assert typed.timezone == "Asia/Kolkata"
    assert typed.is_open is True
    assert typed.duration_minutes == 30
    assert typed.slots[0].starts_at.isoformat() == "2026-10-13T09:00:00+05:30"
    assert typed.slots[0].ends_at.isoformat() == "2026-10-13T09:30:00+05:30"
    assert typed.slots[-1].starts_at.isoformat() == "2026-10-13T17:30:00+05:30"
    assert defaulted.duration_minutes == 30
    assert defaulted.slots[0].ends_at - defaulted.slots[0].starts_at == timedelta(minutes=30)


def test_a_closed_day_and_a_taken_slot(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _at(1, 10, 0))
    with Session(get_engine()) as session:
        closed = find_availability(session, clinic_id, clinician_id, type_id, _day(6), _NOW)
        open_day = find_availability(session, clinic_id, clinician_id, type_id, _day(1), _NOW)
    assert closed.is_open is False
    assert closed.slots == []
    taken = {slot.starts_at.strftime("%H:%M") for slot in open_day.slots}
    assert "10:00" not in taken
    assert "09:45" not in taken
    assert "10:30" in taken


def test_another_clinics_visit_does_not_block(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        other_actor = create_user(
            session,
            other.id,
            "other-desk@x.test",
            "Other Desk",
            "synthetic-password-marker",
            ["receptionist"],
        )
        other_clinician = create_user(
            session,
            other.id,
            "other-clinician@x.test",
            "Other Clinician",
            "synthetic-password-marker",
            ["clinician"],
        )
        other_patient = register_patient(
            session, other.id, other_actor.id, "Sample Bea", _PHONE, None
        )
        other_type = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == other.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        other_patient_id = other_patient.id
        other_type_id = other_type.id
        other_clinician_id = other_clinician.id
        other_actor_id = other_actor.id
        other_id = other.id
    _book(
        other_id, other_actor_id, other_patient_id, other_clinician_id, other_type_id, _at(1, 10, 0)
    )
    with Session(get_engine()) as session:
        slots = find_availability(session, clinic_id, clinician_id, type_id, _day(1), _NOW)
    assert any(slot.starts_at.strftime("%H:%M") == "10:00" for slot in slots.slots)


def test_availability_rejects_a_bad_day_clinician_or_type(database: str) -> None:
    clinic_id, _actor, clinician_id, _patient, type_id = _world()
    with Session(get_engine()) as session:
        receptionist = create_user(
            session,
            clinic_id,
            "front@x.test",
            "Desk Person",
            "synthetic-password-marker",
            ["receptionist"],
        )
        inactive_user = create_user(
            session,
            clinic_id,
            "idle@x.test",
            "Idle Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        inactive_user.is_active = False
        inactive_type = create_appointment_type(session, clinic_id, "Old visit", 30)
        stored = session.get(AppointmentType, inactive_type.id)
        assert stored is not None
        stored.is_active = False
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        other_clinician = create_user(
            session,
            other.id,
            "other-clinician@x.test",
            "Other Clinician",
            "synthetic-password-marker",
            ["clinician"],
        )
        other_type = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == other.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        receptionist_id = receptionist.id
        inactive_user_id = inactive_user.id
        inactive_type_id = inactive_type.id
        other_clinician_id = other_clinician.id
        other_type_id = other_type.id

    cases = [
        (clinician_id, type_id, _day(-1), "date", "before_today"),
        (clinician_id, type_id, _NOW.date() + timedelta(days=366), "date", "beyond_horizon"),
        (uuid4(), type_id, _day(1), "clinician_id", "unknown"),
        (other_clinician_id, type_id, _day(1), "clinician_id", "unknown"),
        (inactive_user_id, type_id, _day(1), "clinician_id", "inactive"),
        (receptionist_id, type_id, _day(1), "clinician_id", "not_clinician"),
        (clinician_id, uuid4(), _day(1), "appointment_type_id", "unknown"),
        (clinician_id, other_type_id, _day(1), "appointment_type_id", "unknown"),
        (clinician_id, inactive_type_id, _day(1), "appointment_type_id", "inactive"),
    ]
    for clinician, type_id_case, day, field, code in cases:
        with Session(get_engine()) as session:
            with pytest.raises(AppointmentFieldError) as caught:
                find_availability(session, clinic_id, clinician, type_id_case, day, _NOW)
        assert caught.value.field == field
        assert caught.value.code == code


def test_booking_stores_a_scheduled_visit_on_the_grid(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    start = _at(1, 10, 0)
    with Session(get_engine()) as session:
        created = book_appointment(
            session, clinic_id, actor_id, patient_id, clinician_id, type_id, start, _NOW
        )
        session.commit()
    assert created.status == "scheduled"
    assert created.starts_at.isoformat() == "2026-10-13T10:00:00+05:30"
    assert created.ends_at.isoformat() == "2026-10-13T10:30:00+05:30"
    assert created.clinician.full_name == "Sample Clinician"
    assert created.appointment_type.name == "Consultation"


def test_booking_rejects_starts_that_availability_would_not_offer(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    naive = datetime(2026, 10, 13, 10, 0)
    cases = [
        (naive, "timezone_naive"),
        (_at(0, 7, 0), "past"),
        (_at(366, 10, 0), "beyond_horizon"),
        (_at(1, 8, 0), "outside_hours"),
        (_at(1, 10, 7), "not_on_grid"),
        (_at(1, 17, 45), "outside_hours"),
    ]
    for start, code in cases:
        with Session(get_engine()) as session:
            with pytest.raises(AppointmentFieldError) as caught:
                book_appointment(
                    session, clinic_id, actor_id, patient_id, clinician_id, type_id, start, _NOW
                )
        assert caught.value.field == "starts_at"
        assert caught.value.code == code
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Appointment)) == 0


def test_booking_rejects_a_bad_patient_clinician_or_type(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    _assert_book_field(clinic_id, actor_id, uuid4(), clinician_id, type_id, "patient_id", "unknown")
    _assert_book_field(clinic_id, actor_id, patient_id, uuid4(), type_id, "clinician_id", "unknown")
    _assert_book_field(
        clinic_id, actor_id, patient_id, clinician_id, uuid4(), "appointment_type_id", "unknown"
    )
    with Session(get_engine()) as session:
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
    _assert_book_field(
        clinic_id, actor_id, patient_id, clinician_id, type_id, "patient_id", "inactive"
    )


def test_a_taken_clinician_slot_and_a_busy_patient(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    with Session(get_engine()) as session:
        second = register_patient(session, clinic_id, actor_id, "Sample Bea", "9000000002", None)
        other_clinician = create_user(
            session,
            clinic_id,
            "two@x.test",
            "Second Clinician",
            "synthetic-password-marker",
            ["clinician"],
        )
        session.commit()
        second_id = second.id
        other_id = other_clinician.id
    _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _at(1, 10, 0))
    with Session(get_engine()) as session:
        with pytest.raises(SlotTakenError):
            book_appointment(
                session, clinic_id, actor_id, second_id, clinician_id, type_id, _at(1, 10, 0), _NOW
            )
    with Session(get_engine()) as session:
        with pytest.raises(PatientBusyError):
            book_appointment(
                session, clinic_id, actor_id, patient_id, other_id, type_id, _at(1, 10, 0), _NOW
            )
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Appointment)) == 1


def test_upcoming_is_the_soonest_blocking_visits_and_hides_other_clinics(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _at(2, 11, 0))
    _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _at(1, 10, 0))
    with Session(get_engine()) as session:
        session.add(
            Appointment(
                id=uuid4(),
                clinic_id=clinic_id,
                patient_id=patient_id,
                clinician_user_id=clinician_id,
                appointment_type_id=type_id,
                starts_at=_at(1, 15, 0),
                ends_at=_at(1, 15, 30),
                status="cancelled",
            )
        )
        session.commit()
    with Session(get_engine()) as session:
        rows = list_upcoming(session, clinic_id, patient_id, _NOW)
    assert [row.starts_at.strftime("%H:%M") for row in rows] == ["10:00", "11:00"]
    assert rows[0].status == "scheduled"
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        session.commit()
        other_id = other.id
    with Session(get_engine()) as session:
        with pytest.raises(PatientNotFoundError):
            list_upcoming(session, other_id, patient_id, _NOW)
        with pytest.raises(PatientNotFoundError):
            list_upcoming(session, clinic_id, uuid4(), _NOW)


def test_upcoming_stops_at_twenty(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    offsets: list[int] = []
    offset = 1
    while len(offsets) < 21:
        if _day(offset).weekday() != 6:
            offsets.append(offset)
        offset += 1
    for booked in offsets:
        _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _at(booked, 10, 0))
    with Session(get_engine()) as session:
        rows = list_upcoming(session, clinic_id, patient_id, _NOW)
    assert len(rows) == 20
    assert rows[0].starts_at.date() == _day(offsets[0])
    assert rows[-1].starts_at.date() == _day(offsets[19])


def _assert_book_field(
    clinic_id: UUID,
    actor_id: UUID,
    patient_id: UUID,
    clinician_id: UUID,
    type_id: UUID,
    field: str,
    code: str,
) -> None:
    with Session(get_engine()) as session:
        with pytest.raises(AppointmentFieldError) as caught:
            book_appointment(
                session,
                clinic_id,
                actor_id,
                patient_id,
                clinician_id,
                type_id,
                _at(1, 10, 0),
                _NOW,
            )
    assert caught.value.field == field
    assert caught.value.code == code


def _book(
    clinic_id: UUID,
    actor_id: UUID,
    patient_id: UUID,
    clinician_id: UUID,
    type_id: UUID,
    start: datetime,
) -> None:
    with Session(get_engine()) as session:
        book_appointment(
            session, clinic_id, actor_id, patient_id, clinician_id, type_id, start, _NOW
        )
        session.commit()


def _world() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "desk@x.test",
            "Sample Desk",
            "synthetic-password-marker",
            ["receptionist"],
        )
        clinician = create_user(
            session,
            clinic.id,
            "clinician@x.test",
            "Sample Clinician",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, "Sample Ada", _PHONE, None)
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        return clinic.id, actor.id, clinician.id, patient.id, consultation.id


def _day(offset: int) -> date:
    return (_NOW + timedelta(days=offset)).date()


def _at(offset: int, hour: int, minute: int) -> datetime:
    day = _day(offset)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=_ZONE)
