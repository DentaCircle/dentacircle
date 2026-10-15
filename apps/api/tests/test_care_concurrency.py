"""Two sessions: one status move wins, and two adds both land."""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine, to_sqlalchemy_url
from dentacircle.models.care_item import CareItem
from dentacircle.services.care_service import (
    InvalidStatusError,
    add_item,
    change_item_status,
    create_plan,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_two_of_the_same_move_yield_one_success(database: str) -> None:
    clinic_id, actor_id, item_id = _world()
    engine = _engine(database)
    both_waiting, stop = _for_update_gate(engine, needed=2)

    def once(_worker: int) -> str:
        with Session(engine) as session:
            try:
                change_item_status(session, clinic_id, actor_id, item_id, "started")
                assert both_waiting.wait(timeout=5)
                session.commit()
            except InvalidStatusError:
                return "invalid"
            return "changed"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(once, (1, 2)))
    finally:
        stop()
        engine.dispose()
    assert sorted(results) == ["changed", "invalid"]
    with Session(get_engine()) as session:
        row = session.get(CareItem, item_id)
        assert row is not None
        assert row.status == "started"


def test_two_adds_to_one_plan_both_succeed(database: str) -> None:
    clinic_id, actor_id, plan_id = _plan_only()
    engine = _engine(database)
    barrier = threading.Barrier(2)

    def once(name: str) -> str:
        with Session(engine) as session:
            add_item(session, clinic_id, actor_id, plan_id, name)
            barrier.wait(timeout=5)
            session.commit()
        return name

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(once, ("First", "Second")))
    finally:
        engine.dispose()
    assert sorted(results) == ["First", "Second"]
    with Session(get_engine()) as session:
        count = session.scalar(
            select(func.count()).select_from(CareItem).where(CareItem.care_plan_id == plan_id)
        )
    assert count == 2


def _for_update_gate(engine: Engine, *, needed: int) -> tuple[threading.Event, Callable[[], None]]:
    """Signal once `needed` row locks have been requested."""
    ready = threading.Event()
    seen = 0
    guard = threading.Lock()

    def before_cursor_execute(*args: object) -> None:
        nonlocal seen
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


def _world() -> tuple[UUID, UUID, UUID]:
    clinic_id, actor_id, plan_id = _plan_only()
    with Session(get_engine()) as session:
        item = add_item(session, clinic_id, actor_id, plan_id, "Sample service")
        session.commit()
        return clinic_id, actor_id, item.id


def _plan_only() -> tuple[UUID, UUID, UUID]:
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
        plan = create_plan(session, clinic.id, actor.id, patient.id, "Sample plan")
        session.commit()
        return clinic.id, actor.id, plan.id
