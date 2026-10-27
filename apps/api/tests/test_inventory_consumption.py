"""Completing a visit takes the type's stock. Short stock does not block the visit."""

import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine, to_sqlalchemy_url
from dentacircle.domain.inventory import BatchStock, consumption_takes
from dentacircle.models.appointment import Appointment
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.inventory_transaction import InventoryTransaction
from dentacircle.repositories.inventory_repository import InventoryRepository
from dentacircle.services.appointment_service import (
    InvalidStatusError,
    cancel_appointment,
    change_status,
)
from dentacircle.services.audit_service import record as record_audit
from dentacircle.services.care_service import add_item, create_plan
from dentacircle.services.care_session_service import record_session
from dentacircle.services.inventory_service import (
    InsufficientStockError,
    add_batch,
    adjust,
    create_category,
    create_item,
    get_item,
    remove_resource_rule,
    restock,
    set_item_status,
    set_resource_rule,
)
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.timeline_support import NOW, World, book, kinds, later, move, world

pytest_plugins = ["tests.timeline_support"]

_TODAY = date(2026, 10, 12)
_SOON = date(2026, 11, 1)
_LATER = date(2026, 12, 1)
_ROLES = ["clinician"]


def test_earliest_expiry_is_used_and_a_blank_expiry_waits() -> None:
    soon = UUID(int=1)
    later_batch = UUID(int=2)
    open_ended = UUID(int=3)
    expired = UUID(int=4)
    empty = UUID(int=5)
    taken = consumption_takes(
        [
            BatchStock(later_batch, "LOT-B", _LATER, 5),
            BatchStock(open_ended, "LOT-C", None, 5),
            BatchStock(soon, "LOT-A", _SOON, 1),
            BatchStock(expired, "LOT-OLD", date(2026, 10, 1), 9),
            BatchStock(empty, "LOT-0", date(2026, 10, 20), 0),
        ],
        4,
        _TODAY,
    )
    assert taken == [(soon, 1), (later_batch, 3)]


def test_the_same_expiry_is_ordered_by_batch_number() -> None:
    first = UUID(int=1)
    second = UUID(int=2)
    taken = consumption_takes(
        [
            BatchStock(second, "LOT-B", _SOON, 5),
            BatchStock(first, "LOT-A", _SOON, 5),
        ],
        1,
        _TODAY,
    )
    assert taken == [(first, 1)]


def test_short_stock_returns_only_what_is_on_hand() -> None:
    only = UUID(int=1)
    assert consumption_takes([BatchStock(only, "LOT", _SOON, 2)], 5, _TODAY) == [(only, 2)]
    assert consumption_takes([], 2, _TODAY) == []


def test_completing_a_visit_consumes_each_rule_once(database: str) -> None:
    clinic = world()
    gloves, _batches = _stock(clinic, "Gloves M", [("LOT-1", _SOON, 5)])
    masks, _mask_batches = _stock(clinic, "Masks", [("LOT-9", _LATER, 3)])
    _rule(clinic, clinic.consultation_id, gloves, 2)
    _rule(clinic, clinic.consultation_id, masks, 1)
    visit = _complete(clinic, clinic.consultation_id)
    assert _taken(gloves) == {("LOT-1", -2)}
    assert _taken(masks) == {("LOT-9", -1)}
    assert _stock_of(clinic, gloves) == 3
    assert _linked(visit) == 2
    assert all(event.changed_fields == [] for event in _audits("inventory_transaction"))
    assert kinds(clinic.clinic_id, clinic.patient_id) == [
        "patient_registered",
        "visit_booked",
        "visit_arrived",
        "visit_started",
        "visit_completed",
    ]
    with pytest.raises(InvalidStatusError):
        with Session(get_engine()) as session:
            change_status(
                session, clinic.clinic_id, clinic.actor_id, _ROLES, visit, "completed", NOW
            )
    assert _consumption_count() == 2


def test_a_rule_spans_batches_and_skips_expired_stock(database: str) -> None:
    clinic = world()
    item_id, _batches = _stock(
        clinic,
        "Gloves M",
        [
            ("LOT-LATE", _LATER, 5),
            ("LOT-SOON", _SOON, 2),
            ("LOT-OLD", _TODAY - timedelta(days=1), 8),
        ],
    )
    _rule(clinic, clinic.consultation_id, item_id, 4)
    _complete(clinic, clinic.consultation_id)
    assert _taken(item_id) == {("LOT-SOON", -2), ("LOT-LATE", -2)}
    assert _stock_of(clinic, item_id) == 11


def test_no_expiry_is_used_after_dated_batches(database: str) -> None:
    clinic = world()
    item_id, _batches = _stock(
        clinic,
        "Gloves M",
        [("LOT-OPEN", None, 5), ("LOT-SOON", _SOON, 1)],
    )
    _rule(clinic, clinic.consultation_id, item_id, 2)
    _complete(clinic, clinic.consultation_id)
    assert _taken(item_id) == {("LOT-SOON", -1), ("LOT-OPEN", -1)}


def test_short_or_missing_stock_still_completes_the_visit(database: str) -> None:
    clinic = world()
    short, _short_batches = _stock(clinic, "Gloves M", [("LOT-1", _SOON, 1)])
    empty, _empty_batches = _stock(clinic, "Masks", [("LOT-2", _SOON, 0)])
    _rule(clinic, clinic.consultation_id, short, 3)
    _rule(clinic, clinic.consultation_id, empty, 2)
    visit = _complete(clinic, clinic.consultation_id)
    assert _taken(short) == {("LOT-1", -1)}
    assert _taken(empty) == set()
    assert _stock_of(clinic, short) == 0
    with Session(get_engine()) as session:
        row = session.get(Appointment, visit)
        assert row is not None
        assert row.status == "completed"


def test_an_inactive_item_is_skipped_and_other_rules_still_run(database: str) -> None:
    clinic = world()
    gloves, _gloves = _stock(clinic, "Gloves M", [("LOT-1", _SOON, 4)])
    masks, _masks = _stock(clinic, "Masks", [("LOT-2", _SOON, 4)])
    _rule(clinic, clinic.consultation_id, gloves, 2)
    _rule(clinic, clinic.consultation_id, masks, 1)
    _deactivate(clinic, gloves)
    _complete(clinic, clinic.consultation_id)
    assert _taken(gloves) == set()
    assert _taken(masks) == {("LOT-2", -1)}
    assert _stock_of(clinic, gloves) == 4


def test_other_statuses_and_a_care_session_consume_nothing(database: str) -> None:
    clinic = world()
    item_id, _batches = _stock(clinic, "Gloves M", [("LOT-1", _SOON, 6)])
    _rule(clinic, clinic.consultation_id, item_id, 2)
    arrived = book(clinic, later(0), clinic.consultation_id)
    move(clinic, arrived, "arrived")
    move(clinic, arrived, "in_progress")
    assert _consumption_count() == 0
    care_item = _care_item(clinic)
    with Session(get_engine()) as session:
        record_session(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            arrived,
            [(care_item, "completed")],
        )
        session.commit()
    assert _consumption_count() == 0
    missed = book(clinic, later(60), clinic.consultation_id)
    move(clinic, missed, "no_show", later(60))
    dropped = book(clinic, later(120), clinic.consultation_id)
    with Session(get_engine()) as session:
        cancel_appointment(session, clinic.clinic_id, clinic.actor_id, dropped, NOW)
        session.commit()
    assert _consumption_count() == 0
    _complete(clinic, clinic.consultation_id, start=later(180))
    assert _consumption_count() == 1


def test_a_failed_consumption_leaves_the_visit_and_the_stock(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic = world()
    item_id, _batches = _stock(clinic, "Gloves M", [("LOT-1", _SOON, 5)])
    _rule(clinic, clinic.consultation_id, item_id, 2)
    visit = book(clinic, later(0), clinic.consultation_id)
    move(clinic, visit, "arrived")
    move(clinic, visit, "in_progress")

    def stop_consumption(*args: object, **kwargs: object) -> None:
        if len(args) >= 4 and args[3] == "inventory_transaction":
            raise RuntimeError("stopped")
        record_audit(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("dentacircle.services.inventory_service.record", stop_consumption)
    with Session(get_engine()) as session:
        with pytest.raises(RuntimeError, match="stopped"):
            change_status(
                session, clinic.clinic_id, clinic.actor_id, _ROLES, visit, "completed", NOW
            )
        session.rollback()
    with Session(get_engine()) as session:
        row = session.get(Appointment, visit)
        assert row is not None
        assert row.status == "in_progress"
    assert _consumption_count() == 0
    assert _stock_of(clinic, item_id) == 5
    assert "visit_completed" not in kinds(clinic.clinic_id, clinic.patient_id)


def test_deleting_a_rule_leaves_past_consumption(database: str) -> None:
    clinic = world()
    item_id, _batches = _stock(clinic, "Gloves M", [("LOT-1", _SOON, 5)])
    _rule(clinic, clinic.consultation_id, item_id, 2)
    _complete(clinic, clinic.consultation_id)
    with Session(get_engine()) as session:
        remove_resource_rule(
            session, clinic.clinic_id, clinic.actor_id, clinic.consultation_id, item_id
        )
        session.commit()
    assert _consumption_count() == 1
    actions = [event.action for event in _audits("procedure_resource_rule")]
    assert actions == ["create", "delete"]
    assert _audits("procedure_resource_rule")[0].changed_fields == []


def test_replacing_a_rule_records_the_field_name_only(database: str) -> None:
    clinic = world()
    item_id, _batches = _stock(clinic, "Gloves M", [("LOT-1", _SOON, 5)])
    _rule(clinic, clinic.consultation_id, item_id, 2)
    _rule(clinic, clinic.consultation_id, item_id, 4)
    updates = [event for event in _audits("procedure_resource_rule") if event.action == "update"]
    assert len(updates) == 1
    assert updates[0].changed_fields == ["quantity"]
    assert "4" not in "".join(updates[0].changed_fields or [])


def test_a_rule_lookup_stays_inside_the_clinic(database: str) -> None:
    clinic = world()
    item_id, _batches = _stock(clinic, "Gloves M", [("LOT-1", _SOON, 5)])
    _rule(clinic, clinic.consultation_id, item_id, 2)
    other_clinic, _other_user = _other_clinic()
    with Session(get_engine()) as session:
        found = InventoryRepository(session, other_clinic).get_rule(clinic.consultation_id, item_id)
    assert found is None


def test_a_completion_and_an_adjustment_cannot_drive_stock_negative(database: str) -> None:
    clinic = world()
    item_id, batches = _stock(clinic, "Gloves M", [("LOT-1", _SOON, 4)])
    _rule(clinic, clinic.consultation_id, item_id, 3)
    visit = book(clinic, later(0), clinic.consultation_id)
    move(clinic, visit, "arrived")
    move(clinic, visit, "in_progress")
    engine = create_engine(
        to_sqlalchemy_url(database),
        pool_size=2,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )
    ready, stop = _batch_lock_gate(engine)

    def adjust_once() -> str:
        with Session(engine) as session:
            try:
                adjust(session, clinic.clinic_id, clinic.actor_id, batches[0], -4, "damaged")
            except InsufficientStockError:
                session.rollback()
                return "short"
            if not ready.wait(timeout=5):
                session.rollback()
                return "timeout"
            session.commit()
            return "adjusted"

    def complete_once() -> str:
        with Session(engine) as session:
            change_status(
                session, clinic.clinic_id, clinic.actor_id, _ROLES, visit, "completed", NOW
            )
            if not ready.wait(timeout=5):
                session.rollback()
                return "timeout"
            session.commit()
            return "completed"

    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                job.result(timeout=10)
                for job in (pool.submit(adjust_once), pool.submit(complete_once))
            ]
    finally:
        stop()
        engine.dispose()
    assert "timeout" not in results
    assert "completed" in results
    with Session(get_engine()) as session:
        row = session.get(Appointment, visit)
        detail = get_item(session, clinic.clinic_id, item_id, NOW)
    assert row is not None and row.status == "completed"
    assert detail.batches[0].quantity in (0, 1)
    assert detail.batches[0].quantity >= 0


def _stock(
    clinic: World, name: str, batches: list[tuple[str, date | None, int]]
) -> tuple[UUID, list[UUID]]:
    with Session(get_engine()) as session:
        category = create_category(session, clinic.clinic_id, clinic.actor_id, f"Group {name}")
        item = create_item(session, clinic.clinic_id, clinic.actor_id, name, category.id, "box", 0)
        session.commit()
        category_id = category.id
        item_id = item.id
    del category_id
    stored: list[UUID] = []
    for number, expiry, quantity in batches:
        with Session(get_engine()) as session:
            batch = add_batch(
                session, clinic.clinic_id, clinic.actor_id, item_id, number, expiry, NOW
            )
            session.commit()
            batch_id = batch.id
        if quantity > 0:
            with Session(get_engine()) as session:
                restock(session, clinic.clinic_id, clinic.actor_id, batch_id, quantity)
                session.commit()
        stored.append(batch_id)
    return item_id, stored


def _rule(clinic: World, type_id: UUID, item_id: UUID, quantity: int) -> None:
    with Session(get_engine()) as session:
        set_resource_rule(session, clinic.clinic_id, clinic.actor_id, type_id, item_id, quantity)
        session.commit()


def _deactivate(clinic: World, item_id: UUID) -> None:
    with Session(get_engine()) as session:
        set_item_status(session, clinic.clinic_id, clinic.actor_id, item_id, "inactive")
        session.commit()


def _complete(clinic: World, type_id: UUID, start: datetime | None = None) -> UUID:
    when = later(0) if start is None else start
    visit = book(clinic, when, type_id)
    move(clinic, visit, "arrived", when)
    move(clinic, visit, "in_progress", when)
    move(clinic, visit, "completed", when)
    return visit


def _care_item(clinic: World) -> UUID:
    with Session(get_engine()) as session:
        plan = create_plan(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "Sample plan"
        )
        item = add_item(session, clinic.clinic_id, clinic.actor_id, plan.id, "Scaling")
        session.commit()
        return item.id


def _taken(item_id: UUID) -> set[tuple[str, int]]:
    from dentacircle.services.inventory_service import list_transactions

    with Session(get_engine()) as session:
        page = list_transactions(session, _clinic_of(item_id), item_id, 1, 20)
    return {
        (row.batch_number, row.quantity_change) for row in page.items if row.type == "consumption"
    }


def _stock_of(clinic: World, item_id: UUID) -> int:
    with Session(get_engine()) as session:
        detail = get_item(session, clinic.clinic_id, item_id, NOW)
    return detail.item.stock


def _linked(visit: UUID) -> int:
    with Session(get_engine()) as session:
        total = session.scalar(
            select(func.count())
            .select_from(InventoryTransaction)
            .where(
                InventoryTransaction.type == "consumption",
                InventoryTransaction.appointment_id == visit,
            )
        )
    return int(total or 0)


def _consumption_count() -> int:
    with Session(get_engine()) as session:
        total = session.scalar(
            select(func.count())
            .select_from(InventoryTransaction)
            .where(InventoryTransaction.type == "consumption")
        )
    return int(total or 0)


def _clinic_of(item_id: UUID) -> UUID:
    with Session(get_engine()) as session:
        from dentacircle.models.inventory_item import InventoryItem

        item = session.get(InventoryItem, item_id)
        assert item is not None
        return item.clinic_id


def _audits(entity_type: str) -> list[AuditEvent]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == entity_type)
                .order_by(AuditEvent.occurred_at, AuditEvent.action)
            )
        )


def _other_clinic() -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Another Synthetic Clinic")
        user = create_user(
            session,
            other.id,
            "other-consumption@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["inventory_admin"],
        )
        session.commit()
        return other.id, user.id


def _batch_lock_gate(engine: Engine) -> tuple[threading.Event, Callable[[], None]]:
    ready = threading.Event()
    seen = 0
    guard = threading.Lock()

    def before_cursor_execute(*args: object) -> None:
        nonlocal seen
        statement = args[2]
        if not isinstance(statement, str):
            return
        folded = statement.lower()
        if "for update" not in folded or "inventory_batch" not in folded:
            return
        with guard:
            seen += 1
            if seen >= 2:
                ready.set()

    event.listen(engine, "before_cursor_execute", before_cursor_execute)

    def stop() -> None:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    return ready, stop
