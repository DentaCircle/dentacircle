"""Two contacted or two books on one follow-up: one wins, the other is refused."""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine, to_sqlalchemy_url
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.follow_up import FollowUp
from dentacircle.services.follow_up_service import (
    FollowUpInvalidStatusError,
    book_follow_up,
    create_manual_follow_up,
    mark_contacted,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 21, 10, 0, tzinfo=_ZONE)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_two_contacted_requests_leave_one_change(database: str) -> None:
    clinic_id, actor_id, patient_id, follow_up_id, _type_id = _world()
    engine = _engine(database)
    patient_locked, stop = _patient_lock_gate(engine, needed=2)

    def once() -> str:
        with Session(engine) as session:
            try:
                mark_contacted(session, clinic_id, actor_id, follow_up_id, _NOW)
            except FollowUpInvalidStatusError:
                return "conflict"
            assert patient_locked.wait(timeout=5)
            session.commit()
        return "contacted"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [job.result(timeout=10) for job in (pool.submit(once), pool.submit(once))]
    finally:
        stop()
        engine.dispose()
    assert sorted(results) == ["conflict", "contacted"]
    with Session(get_engine()) as session:
        row = session.get(FollowUp, follow_up_id)
    assert row is not None
    assert row.status == "contacted"


def test_two_books_create_one_appointment(database: str) -> None:
    clinic_id, actor_id, _patient_id, follow_up_id, type_id = _world()
    engine = _engine(database)
    patient_locked, stop = _patient_lock_gate(engine, needed=2)
    first_start = _NOW.replace(hour=11) + timedelta(days=1)
    while first_start.weekday() == 6:
        first_start += timedelta(days=1)
    second_start = first_start + timedelta(hours=1)

    def once(starts_at: datetime) -> str:
        with Session(engine) as session:
            try:
                book_follow_up(
                    session,
                    clinic_id,
                    actor_id,
                    follow_up_id,
                    actor_id,
                    type_id,
                    starts_at,
                    _NOW,
                )
            except FollowUpInvalidStatusError:
                return "conflict"
            assert patient_locked.wait(timeout=5)
            session.commit()
        return "booked"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                job.result(timeout=10)
                for job in (pool.submit(once, first_start), pool.submit(once, second_start))
            ]
    finally:
        stop()
        engine.dispose()
    assert sorted(results) == ["booked", "conflict"]
    with Session(get_engine()) as session:
        row = session.get(FollowUp, follow_up_id)
        visits = list(session.scalars(select(Appointment)))
        count = session.scalar(select(func.count()).select_from(Appointment))
    assert row is not None
    assert row.status == "booked"
    assert row.booked_appointment_id is not None
    assert len(visits) == 1
    assert count == 1
    assert visits[0].id == row.booked_appointment_id


def _world() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "a@x.test",
            "Synthetic Person",
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
        created = create_manual_follow_up(
            session, clinic.id, actor.id, patient.id, _NOW.date(), _NOW
        )
        session.commit()
        return clinic.id, actor.id, patient.id, created.id, consultation.id


def _patient_lock_gate(
    engine: Engine, *, needed: int
) -> tuple[threading.Event, Callable[[], None]]:
    ready = threading.Event()
    seen = 0
    guard = threading.Lock()

    def before_cursor_execute(*args: object) -> None:
        nonlocal seen
        statement = args[2]
        if not isinstance(statement, str):
            return
        folded = statement.lower()
        if "for update" not in folded or "from patient" not in folded:
            return
        with guard:
            seen += 1
            if seen >= needed:
                ready.set()

    event.listen(engine, "before_cursor_execute", before_cursor_execute)

    def stop() -> None:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    return ready, stop


def _engine(database: str) -> Engine:
    return create_engine(
        to_sqlalchemy_url(database),
        pool_size=2,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )
