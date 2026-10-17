"""Two database sessions: one care session wins, and the other is refused."""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import create_engine, select, text
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
    return _race(database, first, second, refused, session_first=False)


def _race(
    database: str,
    first: Callable[[Session], object],
    second: Callable[[Session], object],
    refused: type[Exception],
    *,
    session_first: bool,
) -> list[str]:
    engine = _engine(database)
    holding = threading.Event()
    # The visit-completing request must see the session blocked on the visit row.
    relation = None if session_first else "appointment"
    competitor_waiting, stop = _for_update_gate(
        database, needed=1, after=holding, relation=relation
    )

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
    database: str,
    *,
    needed: int,
    after: threading.Event | None = None,
    relation: str | None = None,
) -> tuple[threading.Event, Callable[[], None]]:
    """Signal once `needed` row locks are waiting, not merely about to be sent.

    Sending SELECT FOR UPDATE is not the wait. Postgres records the wait in
    pg_locks with granted false.
    """
    ready = threading.Event()
    stopped = threading.Event()
    checker = create_engine(
        to_sqlalchemy_url(database),
        pool_size=1,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )

    def watch() -> None:
        while not stopped.is_set():
            if after is not None and not after.is_set():
                stopped.wait(0.02)
                continue
            with checker.connect() as connection:
                waiting = connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_stat_activity AS activity
                        JOIN pg_locks AS locks ON locks.pid = activity.pid
                        WHERE NOT locks.granted
                          AND locks.locktype = 'transactionid'
                          AND activity.query ILIKE '%for update%'
                          AND (
                            CAST(:relation AS text) IS NULL
                            OR activity.query ILIKE '%' || CAST(:relation AS text) || '%'
                          )
                        """
                    ),
                    {"relation": relation},
                ).scalar_one()
            if waiting >= needed:
                ready.set()
                return
            stopped.wait(0.02)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()

    def stop() -> None:
        stopped.set()
        watcher.join(timeout=1)
        checker.dispose()

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
