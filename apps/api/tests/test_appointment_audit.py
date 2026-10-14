"""A booking writes one audit event. A rejected booking writes nothing."""

from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.appointment import AppointmentFieldError
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.appointment_service import book_appointment
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 12, 8, 0, tzinfo=_ZONE)
_NAME = "Sample Ada"
_START = datetime(2026, 10, 13, 10, 0, tzinfo=_ZONE)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_a_booking_writes_one_event_without_patient_values(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    with Session(get_engine()) as session:
        created = book_appointment(
            session, clinic_id, actor_id, patient_id, clinician_id, type_id, _START, _NOW
        )
        session.commit()
        appointment_id = created.id
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("appointment", appointment_id)
        assert len(events) == 1
        event = events[0]
        assert event.action == "create"
        assert event.entity_type == "appointment"
        assert event.changed_fields == []
        assert event.actor_user_id == actor_id
        row = (
            session.execute(text("SELECT * FROM audit_event WHERE entity_type = 'appointment'"))
            .mappings()
            .one()
        )
        stored = " ".join(str(value) for value in row.values())
        assert _NAME not in stored
        assert "full_name" not in row
        assert "phone" not in row


def test_a_rejected_booking_writes_nothing(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    with Session(get_engine()) as session:
        with pytest.raises(AppointmentFieldError):
            book_appointment(
                session,
                clinic_id,
                actor_id,
                patient_id,
                clinician_id,
                type_id,
                datetime(2026, 10, 13, 8, 0, tzinfo=_ZONE),
                _NOW,
            )
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Appointment)) == 0
        assert _appointment_audits(session) == 0


def test_a_failed_audit_write_does_not_save_the_booking(database: str) -> None:
    clinic_id, _actor_id, clinician_id, patient_id, type_id = _world()
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            book_appointment(
                session, clinic_id, uuid4(), patient_id, clinician_id, type_id, _START, _NOW
            )
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Appointment)) == 0
        assert _appointment_audits(session) == 0


def _appointment_audits(session: Session) -> int:
    count = session.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "appointment")
    )
    return int(count or 0)


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
        patient = register_patient(session, clinic.id, actor.id, _NAME, "9000000001", None)
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        return clinic.id, actor.id, clinician.id, patient.id, consultation.id
