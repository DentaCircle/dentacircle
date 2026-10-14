"""Two moves into one slot: the exclusion constraint keeps one and rejects the other."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine, to_sqlalchemy_url
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.services.appointment_service import (
    PatientBusyError,
    SlotTakenError,
    book_appointment,
    reschedule_appointment,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 14, 8, 0, tzinfo=_ZONE)
_TARGET = datetime(2026, 10, 15, 15, 0, tzinfo=_ZONE)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_two_moves_into_one_slot_yield_one_success(database: str) -> None:
    clinic_id, actor_id, clinician_id, first_id, second_id = _world()
    engine = create_engine(
        to_sqlalchemy_url(database),
        pool_size=2,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )

    def move(appointment_id: UUID) -> str:
        with Session(engine) as session:
            try:
                reschedule_appointment(
                    session, clinic_id, actor_id, appointment_id, _TARGET, None, _NOW
                )
                session.commit()
            except SlotTakenError:
                return "taken"
            return "moved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(move, [first_id, second_id]))
    engine.dispose()
    assert sorted(results) == ["moved", "taken"]
    with Session(get_engine()) as session:
        at_target = session.scalars(
            select(Appointment).where(Appointment.starts_at == _TARGET)
        ).all()
    assert len(at_target) == 1
    assert at_target[0].clinician_user_id == clinician_id


def test_two_moves_of_one_patient_yield_one_success(database: str) -> None:
    clinic_id, actor_id, first_id, second_id = _same_patient()
    engine = create_engine(
        to_sqlalchemy_url(database),
        pool_size=2,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )

    def move(appointment_id: UUID) -> str:
        with Session(engine) as session:
            try:
                reschedule_appointment(
                    session, clinic_id, actor_id, appointment_id, _TARGET, None, _NOW
                )
                session.commit()
            except PatientBusyError:
                return "busy"
            return "moved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(move, [first_id, second_id]))
    engine.dispose()
    assert sorted(results) == ["busy", "moved"]
    with Session(get_engine()) as session:
        at_target = session.scalars(
            select(Appointment).where(Appointment.starts_at == _TARGET)
        ).all()
    assert len(at_target) == 1


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
        first = register_patient(session, clinic.id, actor.id, "Sample Ada", "9000000001", None)
        second = register_patient(session, clinic.id, actor.id, "Sample Bea", "9000000002", None)
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        clinic_id = clinic.id
        actor_id = actor.id
        clinician_id = clinician.id
        type_id = consultation.id
        first_id = first.id
        second_id = second.id
    morning = datetime(2026, 10, 15, 10, 0, tzinfo=_ZONE)
    later = datetime(2026, 10, 15, 11, 0, tzinfo=_ZONE)
    first_visit = _book(clinic_id, actor_id, first_id, clinician_id, type_id, morning)
    second_visit = _book(clinic_id, actor_id, second_id, clinician_id, type_id, later)
    return clinic_id, actor_id, clinician_id, first_visit, second_visit


def _same_patient() -> tuple[UUID, UUID, UUID, UUID]:
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
        first_clinician = create_user(
            session,
            clinic.id,
            "one@x.test",
            "Sample One",
            "synthetic-password-marker",
            ["clinician"],
        )
        second_clinician = create_user(
            session,
            clinic.id,
            "two@x.test",
            "Sample Two",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, "Sample Ada", "9000000001", None)
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        clinic_id = clinic.id
        actor_id = actor.id
        first_clinician_id = first_clinician.id
        second_clinician_id = second_clinician.id
        patient_id = patient.id
        type_id = consultation.id
    morning = datetime(2026, 10, 15, 10, 0, tzinfo=_ZONE)
    later = datetime(2026, 10, 15, 11, 0, tzinfo=_ZONE)
    first_visit = _book(clinic_id, actor_id, patient_id, first_clinician_id, type_id, morning)
    second_visit = _book(clinic_id, actor_id, patient_id, second_clinician_id, type_id, later)
    return clinic_id, actor_id, first_visit, second_visit


def _book(
    clinic_id: UUID,
    actor_id: UUID,
    patient_id: UUID,
    clinician_id: UUID,
    type_id: UUID,
    start: datetime,
) -> UUID:
    with Session(get_engine()) as session:
        created = book_appointment(
            session, clinic_id, actor_id, patient_id, clinician_id, type_id, start, _NOW
        )
        session.commit()
        return created.id
