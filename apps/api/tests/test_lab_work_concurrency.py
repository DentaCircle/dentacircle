"""Two ready calls on one lab item leave one follow-up, because the patient row is locked."""

import threading
from collections.abc import Callable
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine, to_sqlalchemy_url
from dentacircle.models.follow_up import FollowUp
from dentacircle.models.lab_work import LabWork
from dentacircle.services.lab_work_service import (
    InvalidLabStatusError,
    change_lab_status,
    create_lab_work,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 17, 10, 0, tzinfo=_ZONE)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_two_ready_calls_at_once_leave_one_follow_up(database: str) -> None:
    clinic_id, actor_id, patient_id, lab_id = _world()
    engine = _engine(database)
    patient_locked, stop = _patient_lock_gate(engine, needed=2)

    def once() -> str:
        with Session(engine) as session:
            try:
                change_lab_status(session, clinic_id, actor_id, lab_id, "ready", _NOW)
            except InvalidLabStatusError:
                return "invalid"
            assert patient_locked.wait(timeout=5)
            session.commit()
        return "ready"

    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [job.result(timeout=10) for job in (pool.submit(once), pool.submit(once))]
    finally:
        stop()
        engine.dispose()
    assert sorted(results) == ["invalid", "ready"]
    with Session(get_engine()) as session:
        lab = session.get(LabWork, lab_id)
        rows = list(session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)))
    assert lab is not None
    assert lab.status == "ready"
    assert len(rows) == 1
    assert rows[0].status == "scheduled"
    assert rows[0].due_on == _NOW.date()
    assert rows[0].appointment_id is None


def _world() -> tuple[UUID, UUID, UUID, UUID]:
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
        created = create_lab_work(
            session, clinic.id, actor.id, patient.id, "Crown", None, None, _NOW
        )
        session.commit()
        return clinic.id, actor.id, patient.id, created.id


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
