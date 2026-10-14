"""Availability for a move uses the visit's own length and ignores its current span."""

from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.appointment import AppointmentFieldError
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.services.appointment_service import book_appointment, find_availability
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 14, 8, 0, tzinfo=_ZONE)
_START = datetime(2026, 10, 15, 9, 0, tzinfo=_ZONE)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_a_move_ignores_its_own_span_and_keeps_its_length(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id)
    with Session(get_engine()) as session:
        blocked = find_availability(session, clinic_id, clinician_id, type_id, _START.date(), _NOW)
    _retire_type(type_id)
    with Session(get_engine()) as session:
        moved = find_availability(
            session, clinic_id, clinician_id, None, _START.date(), _NOW, appointment_id
        )
    moved_starts = [slot.starts_at for slot in moved.slots]
    assert _START in moved_starts
    assert _START.replace(minute=15) in moved_starts
    assert moved.duration_minutes == 30
    assert _START not in [slot.starts_at for slot in blocked.slots]
    assert _START.replace(minute=15) not in [slot.starts_at for slot in blocked.slots]


def test_exactly_one_of_type_or_visit_is_required(database: str) -> None:
    clinic_id, _actor, clinician_id, _patient, type_id = _world()
    with Session(get_engine()) as session:
        with pytest.raises(AppointmentFieldError) as neither:
            find_availability(session, clinic_id, clinician_id, None, _START.date(), _NOW)
        with pytest.raises(AppointmentFieldError) as both:
            find_availability(
                session, clinic_id, clinician_id, type_id, _START.date(), _NOW, uuid4()
            )
        with pytest.raises(AppointmentFieldError) as missing:
            find_availability(session, clinic_id, clinician_id, None, _START.date(), _NOW, uuid4())
    assert neither.value.field == "appointment_type_id"
    assert neither.value.code == "required"
    assert both.value.field == "reschedule_appointment_id"
    assert both.value.code == "exclusive"
    assert missing.value.field == "reschedule_appointment_id"
    assert missing.value.code == "unknown"


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
        patient = register_patient(session, clinic.id, actor.id, "Sample Ada", "9000000001", None)
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        return clinic.id, actor.id, clinician.id, patient.id, consultation.id


def _book(
    clinic_id: UUID, actor_id: UUID, patient_id: UUID, clinician_id: UUID, type_id: UUID
) -> UUID:
    with Session(get_engine()) as session:
        created = book_appointment(
            session, clinic_id, actor_id, patient_id, clinician_id, type_id, _START, _NOW
        )
        session.commit()
        return created.id


def _retire_type(type_id: UUID) -> None:
    with Session(get_engine()) as session:
        row = session.get(AppointmentType, type_id)
        assert row is not None
        row.duration_minutes = 60
        row.is_active = False
        session.commit()
