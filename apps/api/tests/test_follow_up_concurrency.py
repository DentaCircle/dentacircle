"""Two completes of one patient leave one follow-up, because the patient row is locked."""

import threading
from collections.abc import Callable
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
from dentacircle.services.appointment_service import book_appointment, change_status
from dentacircle.services.care_service import add_item, create_plan
from dentacircle.services.follow_up_service import FollowUpOpenError, create_manual_follow_up
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_FIRST = datetime(2026, 10, 17, 10, 0, tzinfo=_ZONE)
_SECOND = datetime(2026, 10, 17, 11, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_two_completes_at_once_leave_one_follow_up(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id, first_id, second_id = _world()
    engine = _engine(database)
    patient_locked, stop = _patient_lock_gate(engine, needed=2)

    def once(visit_id: UUID, now: datetime) -> str:
        with Session(engine) as session:
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", now)
            assert patient_locked.wait(timeout=5)
            session.commit()
        return "completed"

    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(once, first_id, _FIRST)
            second = pool.submit(once, second_id, _SECOND)
            results = [first.result(timeout=10), second.result(timeout=10)]
    finally:
        stop()
        engine.dispose()
    assert results == ["completed", "completed"]
    with Session(get_engine()) as session:
        rows = list(session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)))
        assert len(rows) == 1
        assert rows[0].status == "scheduled"
        assert rows[0].appointment_id in (first_id, second_id)
        visits = list(
            session.scalars(select(Appointment).where(Appointment.patient_id == patient_id))
        )
        assert {visit.status for visit in visits} == {"completed"}
        assert session.scalar(select(func.count()).select_from(FollowUp)) == 1


def test_two_manual_creates_at_once_leave_one_follow_up(database: str) -> None:
    clinic_id, actor_id, patient_id = _clinic_patient()
    engine = _engine(database)
    patient_locked, stop = _patient_lock_gate(engine, needed=2)
    due_on = _FIRST.date()

    def once() -> str:
        with Session(engine) as session:
            try:
                create_manual_follow_up(session, clinic_id, actor_id, patient_id, due_on, _FIRST)
            except FollowUpOpenError:
                return "open"
            assert patient_locked.wait(timeout=5)
            session.commit()
        return "created"

    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [job.result(timeout=10) for job in (pool.submit(once), pool.submit(once))]
    finally:
        stop()
        engine.dispose()
    assert sorted(results) == ["created", "open"]
    with Session(get_engine()) as session:
        rows = list(session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)))
    assert len(rows) == 1
    assert rows[0].appointment_id is None
    assert rows[0].status == "scheduled"
    assert rows[0].due_on == due_on


def test_a_manual_create_racing_a_completion_leaves_one_follow_up(database: str) -> None:
    clinic_id, actor_id, patient_id, _type_id, visit_id, _second = _world()
    engine = _engine(database)
    patient_locked, stop = _patient_lock_gate(engine, needed=2)
    due_on = _FIRST.date()

    def create() -> str:
        with Session(engine) as session:
            try:
                create_manual_follow_up(session, clinic_id, actor_id, patient_id, due_on, _FIRST)
            except FollowUpOpenError:
                return "open"
            assert patient_locked.wait(timeout=5)
            session.commit()
        return "created"

    def complete() -> str:
        with Session(engine) as session:
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", _FIRST)
            assert patient_locked.wait(timeout=5)
            session.commit()
        return "completed"

    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                job.result(timeout=10) for job in (pool.submit(create), pool.submit(complete))
            ]
    finally:
        stop()
        engine.dispose()
    assert "completed" in results
    assert results.count("created") + results.count("open") == 1
    with Session(get_engine()) as session:
        rows = list(session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)))
        visit = session.get(Appointment, visit_id)
    assert len(rows) == 1
    assert rows[0].status in ("scheduled", "contacted", "booked")
    assert visit is not None
    assert visit.status == "completed"


def _clinic_patient() -> tuple[UUID, UUID, UUID]:
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
        session.commit()
        return clinic.id, actor.id, patient.id


def _patient_lock_gate(
    engine: Engine, *, needed: int
) -> tuple[threading.Event, Callable[[], None]]:
    """Signal once `needed` patient-row locks have been requested."""
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


def _world() -> tuple[UUID, UUID, UUID, UUID, UUID, UUID]:
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
        plan = create_plan(session, clinic.id, actor.id, patient.id, "Sample plan")
        add_item(session, clinic.id, actor.id, plan.id, "Sample service")
        session.commit()
        clinic_id, actor_id, patient_id, type_id = (
            clinic.id,
            actor.id,
            patient.id,
            consultation.id,
        )
    first = _in_progress(clinic_id, actor_id, patient_id, type_id, _FIRST)
    second = _in_progress(clinic_id, actor_id, patient_id, type_id, _SECOND)
    return clinic_id, actor_id, patient_id, type_id, first, second


def _in_progress(
    clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID, start: datetime
) -> UUID:
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            actor_id,
            type_id,
            start,
            start - timedelta(hours=1),
        )
        change_status(session, clinic_id, actor_id, _ROLES, created.id, "arrived", start)
        change_status(session, clinic_id, actor_id, _ROLES, created.id, "in_progress", start)
        session.commit()
        return created.id
