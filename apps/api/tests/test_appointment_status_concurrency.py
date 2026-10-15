"""Two sessions on one visit: the row lock lets one status change win."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine, to_sqlalchemy_url
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.services.appointment_service import (
    InvalidStatusError,
    book_appointment,
    cancel_appointment,
    change_status,
    reschedule_appointment,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_BOOK_NOW = datetime(2026, 10, 14, 8, 0, tzinfo=_ZONE)
_START = datetime(2026, 10, 15, 10, 0, tzinfo=_ZONE)
_NOW = _START
_LATER = datetime(2026, 10, 15, 11, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_two_of_the_same_move_yield_one_success(database: str) -> None:
    clinic_id, actor_id, appointment_id = _world()
    engine = _engine(database)

    def once(_worker: int) -> str:
        with Session(engine) as session:
            try:
                change_status(session, clinic_id, actor_id, _ROLES, appointment_id, "arrived", _NOW)
                session.commit()
            except InvalidStatusError:
                return "invalid"
            return "changed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(once, (1, 2)))
    engine.dispose()
    assert sorted(results) == ["changed", "invalid"]
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.status == "arrived"


def test_a_status_change_and_a_cancel_yield_one_success(database: str) -> None:
    clinic_id, actor_id, appointment_id = _world()
    outcome = _race(database, clinic_id, actor_id, appointment_id, "cancel")
    assert sorted(outcome) == ["changed", "invalid"]
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.status in ("arrived", "cancelled")


def test_a_status_change_and_a_reschedule_yield_one_success(database: str) -> None:
    clinic_id, actor_id, appointment_id = _world()
    outcome = _race(database, clinic_id, actor_id, appointment_id, "reschedule")
    assert sorted(outcome) == ["changed", "invalid"]
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.status == "arrived"
        assert row.starts_at == _START


def _race(
    database: str,
    clinic_id: UUID,
    actor_id: UUID,
    appointment_id: UUID,
    other: str,
) -> list[str]:
    engine = _engine(database)
    locked = threading.Event()

    def change() -> str:
        with Session(engine) as session:
            change_status(session, clinic_id, actor_id, _ROLES, appointment_id, "arrived", _NOW)
            locked.set()
            time.sleep(0.4)
            session.commit()
        return "changed"

    def compete() -> str:
        assert locked.wait(timeout=5)
        with Session(engine) as session:
            try:
                if other == "cancel":
                    cancel_appointment(session, clinic_id, actor_id, appointment_id, _NOW)
                else:
                    reschedule_appointment(
                        session, clinic_id, actor_id, appointment_id, _LATER, None, _NOW
                    )
                session.commit()
            except InvalidStatusError:
                return "invalid"
            return "other"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(change)
        second = pool.submit(compete)
        results = [first.result(timeout=10), second.result(timeout=10)]
    engine.dispose()
    return results


def _engine(database: str) -> Engine:
    return create_engine(
        to_sqlalchemy_url(database),
        pool_size=2,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )


def _world() -> tuple[UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "desk@x.test",
            "Sample Desk",
            "synthetic-password-marker",
            ["clinician"],
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
        clinic_id = clinic.id
        actor_id = actor.id
        clinician_id = clinician.id
        patient_id = patient.id
        type_id = consultation.id
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            clinician_id,
            type_id,
            _START,
            _BOOK_NOW,
        )
        session.commit()
        return clinic_id, actor_id, created.id
