"""Inventory service: names, duplicates, stock movements, audit and rollback."""

import threading
from collections.abc import Callable
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine, to_sqlalchemy_url
from dentacircle.domain.inventory import InventoryFieldError
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.inventory_batch import InventoryBatch
from dentacircle.models.inventory_category import InventoryCategory
from dentacircle.models.inventory_item import InventoryItem
from dentacircle.models.inventory_transaction import InventoryTransaction
from dentacircle.repositories.inventory_repository import InventoryRepository
from dentacircle.services.audit_service import record as record_audit
from dentacircle.services.inventory_service import (
    BatchChanges,
    BatchView,
    CategoryView,
    DuplicateBatchError,
    DuplicateNameError,
    InsufficientStockError,
    InvalidItemStatusError,
    InventoryNotFoundError,
    ItemChanges,
    ItemInactiveError,
    ItemView,
    TransactionView,
    add_batch,
    adjust,
    create_category,
    create_item,
    edit_batch,
    edit_item,
    get_item,
    list_categories,
    list_items,
    list_transactions,
    rename_category,
    restock,
    set_item_status,
)
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.timeline_support import NOW, World, world

pytest_plugins = ["tests.timeline_support"]

_TODAY = date(2026, 10, 12)


def test_a_category_is_trimmed_and_a_repeat_is_refused(database: str) -> None:
    clinic = world()
    created = _category(clinic, "  Consumables  ")
    assert created.name == "Consumables"
    assert created.item_count == 0
    events = _audits("inventory_category")
    assert len(events) == 1
    assert events[0].action == "create"
    assert events[0].changed_fields == []
    with pytest.raises(DuplicateNameError):
        _category(clinic, "consumables")
    assert _count(InventoryCategory) == 1


def test_renaming_to_the_same_name_writes_no_audit_row(database: str) -> None:
    clinic = world()
    created = _category(clinic, "Medicines")
    renamed = _rename(clinic, created.id, "  Medicines  ")
    assert renamed.name == "Medicines"
    assert [event.action for event in _audits("inventory_category")] == ["create"]
    changed = _rename(clinic, created.id, "Medicine")
    assert changed.name == "Medicine"
    updates = [event for event in _audits("inventory_category") if event.action == "update"]
    assert len(updates) == 1
    assert updates[0].changed_fields == ["name"]
    assert "Medicine" not in updates[0].changed_fields
    with pytest.raises(InventoryNotFoundError):
        _rename(clinic, uuid4(), "Other")


def test_categories_are_sorted_by_name_and_count_their_items(database: str) -> None:
    clinic = world()
    medicines = _category(clinic, "Medicines")
    consumables = _category(clinic, "Consumables")
    _item(clinic, "Gloves M", consumables.id)
    with Session(get_engine()) as session:
        listed = list_categories(session, clinic.clinic_id)
    assert [row.name for row in listed] == ["Consumables", "Medicines"]
    assert [row.item_count for row in listed] == [1, 0]
    assert listed[1].id == medicines.id


def test_an_item_starts_active_and_records_a_create_with_no_fields(database: str) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    created = _item(clinic, "  Gloves M  ", category.id, unit="  box  ", threshold=2)
    assert created.status == "active"
    assert created.name == "Gloves M"
    assert created.unit == "box"
    assert created.low_stock_threshold == 2
    assert created.batch_count == 0
    assert created.category.name == "Consumables"
    events = _audits("inventory_item")
    assert [(event.action, event.changed_fields) for event in events] == [("create", [])]
    with pytest.raises(DuplicateNameError):
        _item(clinic, "gloves m", category.id)
    with pytest.raises(InventoryNotFoundError):
        _item(clinic, "Mask", uuid4())


def test_an_unchanged_edit_writes_no_audit_and_a_real_edit_lists_field_names(
    database: str,
) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    other = _category(clinic, "Medicines")
    created = _item(clinic, "Gloves M", category.id, unit="box", threshold=1)
    same = _edit(
        clinic, created.id, ItemChanges(frozenset({"name", "unit"}), "Gloves M", unit="box")
    )
    assert same.name == "Gloves M"
    assert [event.action for event in _audits("inventory_item")] == ["create"]
    edited = _edit(
        clinic,
        created.id,
        ItemChanges(
            frozenset({"name", "category_id", "unit", "low_stock_threshold"}),
            "Gloves L",
            other.id,
            "pair",
            4,
        ),
    )
    assert edited.category.id == other.id
    assert edited.unit == "pair"
    assert edited.low_stock_threshold == 4
    updates = [event for event in _audits("inventory_item") if event.action == "update"]
    assert updates[0].changed_fields == ["name", "category_id", "unit", "low_stock_threshold"]
    assert "Gloves L" not in updates[0].changed_fields


def test_the_same_status_again_is_refused_and_a_move_records_status(database: str) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    created = _item(clinic, "Gloves M", category.id)
    inactive = _status(clinic, created.id, "inactive")
    assert inactive.status == "inactive"
    changes = [event for event in _audits("inventory_item") if event.action == "status_change"]
    assert changes[0].changed_fields == ["status"]
    with pytest.raises(InvalidItemStatusError):
        _status(clinic, created.id, "inactive")
    active = _status(clinic, created.id, "active")
    assert active.status == "active"
    assert _count(InventoryItem) == 1


def test_a_failed_audit_write_leaves_no_category_item_or_batch(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic = world()

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("write failed")

    monkeypatch.setattr("dentacircle.services.inventory_service.record", fail)
    with pytest.raises(RuntimeError):
        _category(clinic, "Consumables")
    assert _count(InventoryCategory) == 0
    assert _audits("inventory_category") == []
    monkeypatch.setattr("dentacircle.services.inventory_service.record", record_audit)
    category = _category(clinic, "Consumables")
    monkeypatch.setattr("dentacircle.services.inventory_service.record", fail)
    with pytest.raises(RuntimeError):
        _item(clinic, "Gloves M", category.id)
    assert _count(InventoryItem) == 0
    monkeypatch.setattr("dentacircle.services.inventory_service.record", record_audit)
    item = _item(clinic, "Gloves M", category.id)
    monkeypatch.setattr("dentacircle.services.inventory_service.record", fail)
    with pytest.raises(RuntimeError):
        _batch(clinic, item.id, "LOT-1")
    assert _count(InventoryBatch) == 0
    assert _audits("inventory_batch") == []


def test_a_batch_keeps_no_quantity_and_an_inactive_item_refuses_a_new_one(
    database: str,
) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    item = _item(clinic, "Gloves M", category.id)
    created = _batch(clinic, item.id, "  LOT-1  ", expiry_on=_TODAY - timedelta(days=1))
    assert created.batch_number == "LOT-1"
    assert created.expiry_on == _TODAY - timedelta(days=1)
    assert created.expired is True
    assert created.quantity == 0
    events = _audits("inventory_batch")
    assert events[0].action == "create"
    assert events[0].changed_fields == []
    _status(clinic, item.id, "inactive")
    with pytest.raises(ItemInactiveError):
        _batch(clinic, item.id, "LOT-2")
    assert _count(InventoryBatch) == 1
    cleared = _edit_batch(
        clinic, created.id, BatchChanges(frozenset({"expiry_on"}), expiry_on=None)
    )
    assert cleared.expiry_on is None
    assert cleared.expired is False
    updates = [event for event in _audits("inventory_batch") if event.action == "update"]
    assert updates[0].changed_fields == ["expiry_on"]


def test_batches_sort_by_expiry_and_a_duplicate_number_is_refused(database: str) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    item = _item(clinic, "Gloves M", category.id)
    later = _batch(clinic, item.id, "LATER", expiry_on=_TODAY + timedelta(days=10))
    none = _batch(clinic, item.id, "NONE")
    early = _batch(clinic, item.id, "EARLY", expiry_on=_TODAY - timedelta(days=2))
    with Session(get_engine()) as session:
        session.execute(
            text(
                "UPDATE inventory_batch SET created_at = created_at - interval '1 hour'"
                " WHERE id = :id"
            ),
            {"id": later.id},
        )
        session.commit()
        detail = get_item(session, clinic.clinic_id, item.id, NOW)
    assert [batch.batch_number for batch in detail.batches] == ["EARLY", "LATER", "NONE"]
    assert detail.batches[0].expired is True
    assert detail.batches[1].expired is False
    assert detail.item.batch_count == 3
    assert early.id == detail.batches[0].id
    assert none.expiry_on is None
    with pytest.raises(DuplicateBatchError):
        _batch(clinic, item.id, "early")
    with pytest.raises(InventoryFieldError) as too_early:
        _batch(clinic, item.id, "OLD", expiry_on=date(1999, 12, 31))
    assert too_early.value.code == "before_2000"
    with pytest.raises(InventoryNotFoundError):
        _batch(clinic, uuid4(), "LOT-9")


def test_the_same_name_in_another_clinic_is_allowed_and_ids_do_not_cross(
    database: str,
) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    item = _item(clinic, "Gloves M", category.id)
    other_clinic, other_user = _other_clinic()
    with Session(get_engine()) as session:
        other_category = create_category(session, other_clinic, other_user, "Consumables")
        other_item = create_item(
            session, other_clinic, other_user, "Gloves M", other_category.id, "box", 0
        )
        session.commit()
    assert other_item.name == "Gloves M"
    with pytest.raises(InventoryNotFoundError):
        with Session(get_engine()) as session:
            get_item(session, other_clinic, item.id, NOW)
    with pytest.raises(InventoryNotFoundError):
        _item(clinic, "Mask", other_category.id)


def test_a_category_from_another_clinic_is_not_found_for_a_new_item(database: str) -> None:
    clinic = world()
    other_clinic, other_user = _other_clinic()
    with Session(get_engine()) as session:
        other = create_category(session, other_clinic, other_user, "Medicines")
        session.commit()
        repository = InventoryRepository(session, clinic.clinic_id)
        assert repository.get_category(other.id) is None
    with pytest.raises(InventoryNotFoundError):
        _item(clinic, "Mask", other.id)


def test_the_item_list_filters_and_an_unknown_category_is_an_empty_page(database: str) -> None:
    clinic = world()
    consumables = _category(clinic, "Consumables")
    medicines = _category(clinic, "Medicines")
    gloves = _item(clinic, "Gloves M", consumables.id)
    _item(clinic, "Medicine A", medicines.id, unit="tablets")
    _status(clinic, gloves.id, "inactive")
    with Session(get_engine()) as session:
        active = list_items(session, clinic.clinic_id, "active", None, None, 1, 20)
        inactive = list_items(session, clinic.clinic_id, "inactive", None, "GLOVE", 1, 20)
        missing = list_items(session, clinic.clinic_id, "all", uuid4(), None, 1, 20)
    assert [row.name for row in active.items] == ["Medicine A"]
    assert [row.name for row in inactive.items] == ["Gloves M"]
    assert missing.total == 0
    assert missing.items == []


def test_stock_is_the_sum_of_movements_including_an_expired_batch(database: str) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    item = _item(clinic, "Gloves M", category.id)
    expired = _batch(clinic, item.id, "OLD", expiry_on=_TODAY - timedelta(days=3))
    current = _batch(clinic, item.id, "NEW", expiry_on=_TODAY + timedelta(days=30))
    added = _restock(clinic, expired.id, 10)
    assert added.type == "restock"
    assert added.reason is None
    assert added.quantity_change == 10
    assert added.batch_number == "OLD"
    assert added.recorded_by == "Sample Desk"
    assert added.created_at.utcoffset() == timedelta(hours=5, minutes=30)
    _restock(clinic, current.id, 4)
    written = _adjust(clinic, current.id, -1, "damaged")
    assert written.type == "adjustment"
    assert written.reason == "damaged"
    assert written.quantity_change == -1
    with Session(get_engine()) as session:
        detail = get_item(session, clinic.clinic_id, item.id, NOW)
        listed = list_items(session, clinic.clinic_id, "all", None, None, 1, 20)
    assert detail.item.stock == 13
    assert listed.items[0].stock == 13
    quantities = {batch.batch_number: batch.quantity for batch in detail.batches}
    assert quantities == {"OLD": 10, "NEW": 3}
    stored = _count(InventoryBatch)
    assert stored == 2
    with Session(get_engine()) as session:
        row = session.get(InventoryBatch, expired.id)
    assert row is not None
    assert "quantity" not in row.__table__.columns


def test_a_removal_below_zero_writes_nothing_and_an_inactive_item_can_be_written_off(
    database: str,
) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    item = _item(clinic, "Gloves M", category.id)
    batch = _batch(clinic, item.id, "LOT-1")
    _restock(clinic, batch.id, 5)
    with pytest.raises(InsufficientStockError):
        _adjust(clinic, batch.id, -6, "expired")
    assert _count_transactions() == 1
    _status(clinic, item.id, "inactive")
    with pytest.raises(ItemInactiveError):
        _restock(clinic, batch.id, 1)
    assert _count_transactions() == 1
    corrected = _adjust(clinic, batch.id, -5, "correction")
    assert corrected.quantity_change == -5
    with pytest.raises(InventoryFieldError) as positive:
        _adjust(clinic, batch.id, 1, "damaged")
    assert positive.value.code == "must_be_negative"
    assert _count_transactions() == 2
    with Session(get_engine()) as session:
        detail = get_item(session, clinic.clinic_id, item.id, NOW)
    assert detail.item.stock == 0
    assert detail.batches[0].quantity == 0


def test_a_failed_audit_write_leaves_no_transaction(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    item = _item(clinic, "Gloves M", category.id)
    batch = _batch(clinic, item.id, "LOT-1")
    seen: list[tuple[str, str, list[str] | None]] = []

    def spy(
        session: Session,
        clinic_id: UUID,
        actor_user_id: UUID,
        entity_type: str,
        entity_id: UUID,
        action: str,
        changed_fields: list[str] | None = None,
    ) -> None:
        seen.append((entity_type, action, changed_fields))
        record_audit(
            session, clinic_id, actor_user_id, entity_type, entity_id, action, changed_fields
        )

    monkeypatch.setattr("dentacircle.services.inventory_service.record", spy)
    created = _restock(clinic, batch.id, 424242)
    assert created.quantity_change == 424242
    assert seen[-1] == ("inventory_transaction", "create", [])
    assert "424242" not in str(seen[-1])
    events = _audits("inventory_transaction")
    assert [(event.action, event.changed_fields) for event in events] == [("create", [])]

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("write failed")

    monkeypatch.setattr("dentacircle.services.inventory_service.record", fail)
    with pytest.raises(RuntimeError):
        _adjust(clinic, batch.id, -1, "damaged")
    assert _count_transactions() == 1
    assert len(_audits("inventory_transaction")) == 1


def test_history_is_newest_first_and_another_clinic_cannot_see_the_batch(database: str) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    item = _item(clinic, "Gloves M", category.id)
    first = _batch(clinic, item.id, "LOT-1")
    second = _batch(clinic, item.id, "LOT-2")
    _restock(clinic, first.id, 2)
    _adjust(clinic, second.id, 3, "correction")
    _adjust(clinic, first.id, -1, "expired")
    with Session(get_engine()) as session:
        page = list_transactions(session, clinic.clinic_id, item.id, 1, 2)
        empty = list_transactions(session, clinic.clinic_id, item.id, 2, 2)
        none = list_items(session, clinic.clinic_id, "all", None, "mask", 1, 20)
    assert page.total == 3
    assert [(row.batch_number, row.quantity_change) for row in page.items] == [
        ("LOT-1", -1),
        ("LOT-2", 3),
    ]
    assert empty.items[0].quantity_change == 2
    assert empty.page == 2
    assert none.total == 0
    other_clinic, other_user = _other_clinic()
    with Session(get_engine()) as session:
        assert InventoryRepository(session, other_clinic).get_batch(first.id) is None
    with pytest.raises(InventoryNotFoundError):
        with Session(get_engine()) as session:
            restock(session, other_clinic, other_user, first.id, 1)
    with pytest.raises(InventoryNotFoundError):
        with Session(get_engine()) as session:
            list_transactions(session, other_clinic, item.id, 1, 20)
    assert _count_transactions() == 3


def test_two_removals_of_the_last_units_yield_one_success(database: str) -> None:
    clinic = world()
    category = _category(clinic, "Consumables")
    item = _item(clinic, "Gloves M", category.id)
    batch = _batch(clinic, item.id, "LOT-1")
    _restock(clinic, batch.id, 5)
    engine = create_engine(
        to_sqlalchemy_url(database),
        pool_size=2,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )
    ready, stop = _batch_lock_gate(engine)

    def once() -> str:
        with Session(engine) as session:
            try:
                adjust(session, clinic.clinic_id, clinic.actor_id, batch.id, -5, "damaged")
            except InsufficientStockError:
                session.rollback()
                return "short"
            if not ready.wait(timeout=5):
                session.rollback()
                return "timeout"
            session.commit()
            return "ok"

    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [job.result(timeout=10) for job in (pool.submit(once), pool.submit(once))]
    finally:
        stop()
        engine.dispose()
    assert sorted(results) == ["ok", "short"]
    with Session(get_engine()) as session:
        detail = get_item(session, clinic.clinic_id, item.id, NOW)
    assert detail.batches[0].quantity == 0
    assert _count_transactions() == 2


def _category(clinic: World, name: str) -> CategoryView:
    with Session(get_engine()) as session:
        created = create_category(session, clinic.clinic_id, clinic.actor_id, name)
        session.commit()
        return created


def _rename(clinic: World, category_id: UUID, name: str) -> CategoryView:
    with Session(get_engine()) as session:
        renamed = rename_category(session, clinic.clinic_id, clinic.actor_id, category_id, name)
        session.commit()
        return renamed


def _item(
    clinic: World,
    name: str,
    category_id: UUID,
    *,
    unit: str = "box",
    threshold: int = 0,
) -> ItemView:
    with Session(get_engine()) as session:
        created = create_item(
            session, clinic.clinic_id, clinic.actor_id, name, category_id, unit, threshold
        )
        session.commit()
        return created


def _edit(clinic: World, item_id: UUID, changes: ItemChanges) -> ItemView:
    with Session(get_engine()) as session:
        edited = edit_item(session, clinic.clinic_id, clinic.actor_id, item_id, changes)
        session.commit()
        return edited


def _status(clinic: World, item_id: UUID, status: str) -> ItemView:
    with Session(get_engine()) as session:
        moved = set_item_status(session, clinic.clinic_id, clinic.actor_id, item_id, status)
        session.commit()
        return moved


def _batch(
    clinic: World, item_id: UUID, batch_number: str, expiry_on: date | None = None
) -> BatchView:
    with Session(get_engine()) as session:
        created = add_batch(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            item_id,
            batch_number,
            expiry_on,
            NOW,
        )
        session.commit()
        return created


def _edit_batch(clinic: World, batch_id: UUID, changes: BatchChanges) -> BatchView:
    with Session(get_engine()) as session:
        edited = edit_batch(session, clinic.clinic_id, clinic.actor_id, batch_id, changes, NOW)
        session.commit()
        return edited


def _other_clinic() -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Another Synthetic Clinic")
        user = create_user(
            session,
            other.id,
            "other@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["inventory_admin"],
        )
        session.commit()
        return other.id, user.id


def _audits(entity_type: str) -> list[AuditEvent]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == entity_type)
                .order_by(AuditEvent.occurred_at, AuditEvent.action)
            )
        )


def _restock(clinic: World, batch_id: UUID, quantity: int) -> TransactionView:
    with Session(get_engine()) as session:
        created = restock(session, clinic.clinic_id, clinic.actor_id, batch_id, quantity)
        session.commit()
        return created


def _adjust(clinic: World, batch_id: UUID, quantity_change: int, reason: str) -> TransactionView:
    with Session(get_engine()) as session:
        created = adjust(
            session, clinic.clinic_id, clinic.actor_id, batch_id, quantity_change, reason
        )
        session.commit()
        return created


def _count_transactions() -> int:
    with Session(get_engine()) as session:
        total = session.scalar(select(func.count()).select_from(InventoryTransaction))
    return int(total or 0)


def _batch_lock_gate(engine: Engine) -> tuple[threading.Event, Callable[[], None]]:
    """Signal once two inventory_batch row locks have been requested."""
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


def _count(model: type[InventoryCategory] | type[InventoryItem] | type[InventoryBatch]) -> int:
    with Session(get_engine()) as session:
        total = session.scalar(select(func.count()).select_from(model))
    return int(total or 0)


def test_alerts_roll_over_on_clinic_day_without_writing(database: str) -> None:
    from datetime import UTC, datetime

    clinic = world()
    category = _category(clinic, "Supplies")
    item = _item(clinic, "Stock", category.id, threshold=2)
    batch = _batch(clinic, item.id, "EXP", date(2026, 10, 12))
    _restock(clinic, batch.id, 2)
    before_audits = len(_audits("inventory_transaction"))
    with Session(get_engine()) as session:
        before = datetime(2026, 10, 12, 18, 29, tzinfo=UTC)
        after = datetime(2026, 10, 12, 18, 30, tzinfo=UTC)
        first = get_item(session, clinic.clinic_id, item.id, before)
        second = get_item(session, clinic.clinic_id, item.id, after)
        listing = list_items(
            session, clinic.clinic_id, "active", None, None, 1, 20, "attention", after
        )
    assert (first.item.stock, first.item.usable_stock, first.item.alerts) == (
        2,
        2,
        ("low_stock", "expiring_soon"),
    )
    assert (second.item.stock, second.item.usable_stock, second.item.alerts) == (
        2,
        0,
        ("out_of_stock", "expired"),
    )
    assert listing.items[0].alerts == second.item.alerts
    assert len(_audits("inventory_transaction")) == before_audits
