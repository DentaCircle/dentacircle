"""Two cancels, or a cancel racing completion, leave the follow-up in one state."""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine, to_sqlalchemy_url
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.follow_up import FollowUp
from dentacircle.services.appointment_service import change_status
from dentacircle.services.follow_up_service import (
    FollowUpInvalidStatusError,
    book_follow_up,
    cancel_follow_up,
    create_manual_follow_up,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_BEFORE = datetime(2026, 10, 20, 9, 0, tzinfo=_ZONE)
_START = datetime(2026, 10, 20, 10, 0, tzinfo=_ZONE)
_NOW = datetime(2026, 10, 20, 15, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_two_cancels_at_once_leave_one_winner(database: str) -> None:
    clinic_id, actor_id, follow_up_id = _scheduled()
    engine = _engine(database)
    patient_locked, stop = _patient_lock_gate(engine, needed=2)

    def once() -> str:
        with Session(engine) as session:
            try:
                cancel_follow_up(session, clinic_id, actor_id, follow_up_id)
            except FollowUpInvalidStatusError:
                return "conflict"
            assert patient_locked.wait(timeout=5)
            session.commit()
        return "cancelled"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [job.result(timeout=10) for job in (pool.submit(once), pool.submit(once))]
    finally:
        stop()
        engine.dispose()
    assert sorted(results) == ["cancelled", "conflict"]
    with Session(get_engine()) as session:
        row = session.get(FollowUp, follow_up_id)
    assert row is not None
    assert row.status == "cancelled"


def test_a_cancel_racing_completion_ends_in_one_state(database: str) -> None:
    clinic_id, actor_id, patient_id, follow_up_id, visit_id = _booked_in_progress()
    engine = _engine(database)
    patient_locked, stop = _patient_lock_gate(engine, needed=2)

    def cancel() -> str:
        with Session(engine) as session:
            try:
                cancel_follow_up(session, clinic_id, actor_id, follow_up_id)
            except FollowUpInvalidStatusError:
                return "conflict"
            assert patient_locked.wait(timeout=5)
            session.commit()
        return "cancelled"

    def complete() -> str:
        with Session(engine) as session:
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", _NOW)
            assert patient_locked.wait(timeout=5)
            session.commit()
        return "completed"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                job.result(timeout=10) for job in (pool.submit(cancel), pool.submit(complete))
            ]
    finally:
        stop()
        engine.dispose()
    assert "completed" in results
    assert results.count("cancelled") + results.count("conflict") == 1
    with Session(get_engine()) as session:
        row = session.get(FollowUp, follow_up_id)
        visit = session.get(Appointment, visit_id)
        rows = list(session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)))
    assert row is not None
    assert visit is not None
    assert visit.status == "completed"
    assert len(rows) == 1
    assert row.status in ("completed", "cancelled")
    assert row.status != "booked"


def _scheduled() -> tuple[UUID, UUID, UUID]:
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
        created = create_manual_follow_up(
            session, clinic.id, actor.id, patient.id, _NOW.date(), _BEFORE
        )
        session.commit()
        return clinic.id, actor.id, created.id


def _booked_in_progress() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    clinic_id, actor_id, follow_up_id = _scheduled()
    with Session(get_engine()) as session:
        row = session.get(FollowUp, follow_up_id)
        assert row is not None
        patient_id = row.patient_id
        consultation = next(
            item
            for item in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic_id)
            )
            if item.name == "Consultation"
        )
        visit = book_follow_up(
            session,
            clinic_id,
            actor_id,
            follow_up_id,
            actor_id,
            consultation.id,
            _START,
            _BEFORE,
        )
        change_status(session, clinic_id, actor_id, _ROLES, visit.id, "arrived", _NOW)
        change_status(session, clinic_id, actor_id, _ROLES, visit.id, "in_progress", _NOW)
        session.commit()
        visit_id = visit.id
    return clinic_id, actor_id, patient_id, follow_up_id, visit_id


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
