"""Two bookings of one slot: the exclusion constraint keeps one and rejects the other."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from psycopg.errors import DeadlockDetected
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine, to_sqlalchemy_url
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.services.appointment_service import SlotTakenError, book_appointment
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 12, 8, 0, tzinfo=_ZONE)
_START = datetime(2026, 10, 13, 10, 0, tzinfo=_ZONE)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_two_bookings_of_one_slot_yield_one_row(database: str) -> None:
    clinic_id, actor_id, clinician_id, first_patient, second_patient, type_id = _world()
    engine = create_engine(
        to_sqlalchemy_url(database),
        pool_size=2,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )

    def book(patient_id: UUID) -> str:
        for attempt in range(3):
            with Session(engine) as session:
                try:
                    book_appointment(
                        session,
                        clinic_id,
                        actor_id,
                        patient_id,
                        clinician_id,
                        type_id,
                        _START,
                        _NOW,
                    )
                    session.commit()
                    return "booked"
                except SlotTakenError:
                    session.rollback()
                    return "taken"
                except OperationalError as exc:
                    session.rollback()
                    if isinstance(exc.orig, DeadlockDetected) and attempt < 2:
                        continue
                    raise
        return "taken"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(book, [first_patient, second_patient]))
    engine.dispose()
    assert sorted(results) == ["booked", "taken"]
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Appointment)) == 1


def _world() -> tuple[UUID, UUID, UUID, UUID, UUID, UUID]:
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
        return clinic.id, actor.id, clinician.id, first.id, second.id, consultation.id
