"""Two database sessions: one care session wins, and the other is refused."""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
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
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_session import CareSession
from dentacircle.services.appointment_service import (
    InvalidStatusError as AppointmentStatusError,
)
from dentacircle.services.appointment_service import (
    book_appointment,
    cancel_appointment,
    change_status,
)
from dentacircle.services.care_service import (
    InvalidStatusError,
    add_item,
    change_item_status,
    create_plan,
)
from dentacircle.services.care_session_service import (
    InvalidVisitStatusError,
    SessionExistsError,
    record_session,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_START = datetime(2026, 10, 17, 10, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_two_sessions_for_one_visit_yield_one_success(database: str) -> None:
    clinic_id, actor_id, visit_id, item_id = _world("arrived")
    outcome = _race_session(
        database,
        lambda session: record_session(
            session, clinic_id, actor_id, visit_id, [(item_id, "started")]
        ),
        lambda session: record_session(
            session, clinic_id, actor_id, visit_id, [(item_id, "completed")]
        ),
        SessionExistsError,
    )
    assert sorted(outcome) == ["other-invalid", "saved"]
    with Session(get_engine()) as session:
        assert session.scalar(select(CareSession).where(CareSession.appointment_id == visit_id))
        row = session.get(CareItem, item_id)
        assert row is not None
        assert row.status == "started"


def test_a_session_and_a_manual_move_yield_one_success(database: str) -> None:
    clinic_id, actor_id, visit_id, item_id = _world("arrived")
    outcome = _race_session(
        database,
        lambda session: record_session(
            session, clinic_id, actor_id, visit_id, [(item_id, "completed")]
        ),
        lambda session: change_item_status(session, clinic_id, actor_id, item_id, "started"),
        InvalidStatusError,
    )
    assert sorted(outcome) == ["other-invalid", "saved"]
    with Session(get_engine()) as session:
        row = session.get(CareItem, item_id)
        assert row is not None
        assert row.status == "completed"
        assert session.scalar(select(CareSession).where(CareSession.appointment_id == visit_id))


def test_a_completed_visit_blocks_the_waiting_session(database: str) -> None:
    clinic_id, actor_id, visit_id, item_id = _world("in_progress")
    outcome = _race_other_first(
        database,
        lambda session: change_status(
            session, clinic_id, actor_id, _ROLES, visit_id, "completed", _START
        ),
        lambda session: record_session(
            session, clinic_id, actor_id, visit_id, [(item_id, "started")]
        ),
        InvalidVisitStatusError,
    )
    assert sorted(outcome) == ["other-invalid", "saved"]
    with Session(get_engine()) as session:
        visit = session.get(Appointment, visit_id)
        assert visit is not None
        assert visit.status == "completed"
        assert (
            session.scalar(select(CareSession).where(CareSession.appointment_id == visit_id))
            is None
        )
        row = session.get(CareItem, item_id)
        assert row is not None
        assert row.status == "planned"


def test_a_session_and_a_cancel_yield_one_success(database: str) -> None:
    clinic_id, actor_id, visit_id, item_id = _world("arrived")
    outcome = _race_session(
        database,
        lambda session: record_session(
            session, clinic_id, actor_id, visit_id, [(item_id, "started")]
        ),
        lambda session: cancel_appointment(session, clinic_id, actor_id, visit_id, _START),
        AppointmentStatusError,
    )
    assert sorted(outcome) == ["other-invalid", "saved"]
    with Session(get_engine()) as session:
        visit = session.get(Appointment, visit_id)
        assert visit is not None
        assert visit.status == "arrived"


def _race_session(
    database: str,
    first: Callable[[Session], object],
    second: Callable[[Session], object],
    refused: type[Exception],
) -> list[str]:
    """The session holds its locks until the other request is blocked on one."""
    return _race(database, first, second, refused, session_first=True)


def _race_other_first(
    database: str,
    first: Callable[[Session], object],
    second: Callable[[Session], object],
    refused: type[Exception],
) -> list[str]:
    return _race(database, first, second, refused, session_first=True)


def _race(
    database: str,
    first: Callable[[Session], object],
    second: Callable[[Session], object],
    refused: type[Exception],
    *,
    session_first: bool,
) -> list[str]:
    del session_first
    engine = _engine(database)
    holding = threading.Event()
    competitor_waiting, stop = _for_update_gate(engine, needed=1, after=holding)

    def lead() -> str:
        with Session(engine) as session:
            first(session)
            holding.set()
            assert competitor_waiting.wait(timeout=5)
            session.commit()
        return "saved"

    def compete() -> str:
        assert holding.wait(timeout=5)
        with Session(engine) as session:
            try:
                second(session)
                session.commit()
            except refused:
                return "other-invalid"
            return "other"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            started = pool.submit(lead)
            followed = pool.submit(compete)
            return [started.result(timeout=10), followed.result(timeout=10)]
    finally:
        stop()
        engine.dispose()


def _for_update_gate(
    engine: Engine, *, needed: int, after: threading.Event | None = None
) -> tuple[threading.Event, Callable[[], None]]:
    ready = threading.Event()
    seen = 0
    guard = threading.Lock()

    def before_cursor_execute(*args: object) -> None:
        nonlocal seen
        if after is not None and not after.is_set():
            return
        statement = args[2]
        if not isinstance(statement, str) or "for update" not in statement.lower():
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


def _world(status: str) -> tuple[UUID, UUID, UUID, UUID]:
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
        item = add_item(session, clinic.id, actor.id, plan.id, "Sample service")
        session.commit()
        clinic_id, actor_id, patient_id = clinic.id, actor.id, patient.id
        type_id, item_id = consultation.id, item.id
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            actor_id,
            type_id,
            _START,
            _START - timedelta(hours=1),
        )
        session.commit()
        visit_id = created.id
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "arrived", _START)
        if status == "in_progress":
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "in_progress", _START)
        session.commit()
    return clinic_id, actor_id, visit_id, item_id
