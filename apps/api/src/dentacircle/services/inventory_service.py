"""One clinic's categories, items, batches and append-only stock movements."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from psycopg.errors import ForeignKeyViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.domain.inventory import (
    BATCH_AUDIT_FIELDS,
    CATEGORY_AUDIT_FIELDS,
    ITEM_AUDIT_FIELDS,
    InventoryFieldError,
    changed_field_names,
    check_adjustment_reason,
    check_adjustment_sign,
    check_item_status,
    check_quantity_change,
    check_restock_quantity,
    check_threshold,
    clean_batch_number,
    clean_category_name,
    clean_item_name,
    clean_unit,
    expiry_problem,
    is_expired,
)
from dentacircle.models.app_user import AppUser
from dentacircle.models.inventory_batch import InventoryBatch
from dentacircle.models.inventory_category import InventoryCategory
from dentacircle.models.inventory_item import InventoryItem
from dentacircle.models.inventory_transaction import InventoryTransaction
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.inventory_repository import InventoryRepository
from dentacircle.services.audit_service import record
from dentacircle.services.clinic_day_service import ClinicNotFoundError


class DuplicateNameError(Exception):
    """The name is already used in this clinic, ignoring case."""


class DuplicateBatchError(Exception):
    """The batch number is already used on this item, ignoring case."""


class InventoryNotFoundError(Exception):
    """No such category, item or batch in the caller's clinic."""


class ItemInactiveError(Exception):
    """An inactive item cannot gain a batch or a restock. An adjustment is still allowed."""


class InsufficientStockError(Exception):
    """The movement would take the batch below zero. Nothing is written."""


class InvalidItemStatusError(Exception):
    """The item already has this status."""


@dataclass(frozen=True)
class CategoryView:
    id: UUID
    name: str
    item_count: int


@dataclass(frozen=True)
class CategoryLink:
    id: UUID
    name: str


@dataclass(frozen=True)
class ItemView:
    id: UUID
    name: str
    category: CategoryLink
    unit: str
    low_stock_threshold: int
    status: str
    batch_count: int
    stock: int


@dataclass(frozen=True)
class BatchView:
    id: UUID
    batch_number: str
    expiry_on: date | None
    expired: bool
    quantity: int
    created_at: datetime


@dataclass(frozen=True)
class TransactionView:
    id: UUID
    type: str
    reason: str | None
    quantity_change: int
    batch_id: UUID
    batch_number: str
    recorded_by: str
    created_at: datetime


@dataclass(frozen=True)
class TransactionPage:
    items: list[TransactionView]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class ItemDetail:
    item: ItemView
    batches: list[BatchView]


@dataclass(frozen=True)
class ItemPage:
    items: list[ItemView]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class ItemChanges:
    fields: frozenset[str]
    name: str | None = None
    category_id: UUID | None = None
    unit: str | None = None
    low_stock_threshold: int | None = None


@dataclass(frozen=True)
class BatchChanges:
    fields: frozenset[str]
    batch_number: str | None = None
    expiry_on: date | None = None


def list_categories(session: Session, clinic_id: UUID) -> list[CategoryView]:
    rows = InventoryRepository(session, clinic_id).list_categories()
    return [CategoryView(category.id, category.name, count) for category, count in rows]


def create_category(
    session: Session, clinic_id: UUID, actor_user_id: UUID, name: str
) -> CategoryView:
    cleaned = clean_category_name(name)
    repository = InventoryRepository(session, clinic_id)
    if repository.find_category_by_name(cleaned) is not None:
        raise DuplicateNameError
    category = InventoryCategory(id=uuid4(), name=cleaned)
    repository.add_category(category)
    record(
        session,
        clinic_id,
        actor_user_id,
        "inventory_category",
        category.id,
        "create",
        changed_fields=[],
    )
    _flush(session, duplicate=DuplicateNameError)
    session.refresh(category)
    return CategoryView(category.id, category.name, 0)


def rename_category(
    session: Session, clinic_id: UUID, actor_user_id: UUID, category_id: UUID, name: str
) -> CategoryView:
    cleaned = clean_category_name(name)
    repository = InventoryRepository(session, clinic_id)
    category = repository.get_category(category_id, lock=True)
    if category is None:
        raise InventoryNotFoundError
    if cleaned == category.name:
        return _category_view(repository, category)
    taken = repository.find_category_by_name(cleaned)
    if taken is not None and taken.id != category.id:
        raise DuplicateNameError
    changed = changed_field_names({"name": category.name}, {"name": cleaned}, CATEGORY_AUDIT_FIELDS)
    category.name = cleaned
    if changed:
        record(
            session,
            clinic_id,
            actor_user_id,
            "inventory_category",
            category.id,
            "update",
            changed_fields=changed,
        )
    _flush(session, duplicate=DuplicateNameError)
    session.refresh(category)
    return _category_view(repository, category)


def list_items(
    session: Session,
    clinic_id: UUID,
    status: str,
    category_id: UUID | None,
    query: str | None,
    page: int,
    page_size: int,
) -> ItemPage:
    stored_status = None if status == "all" else status
    needle = None if query is None or query.strip() == "" else query.strip()
    rows, total = InventoryRepository(session, clinic_id).list_items(
        stored_status, category_id, needle, page, page_size
    )
    return ItemPage(
        items=[
            _item_view(item, category, count, on_hand) for item, category, count, on_hand in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_item(session: Session, clinic_id: UUID, item_id: UUID, now: datetime) -> ItemDetail:
    repository = InventoryRepository(session, clinic_id)
    found = repository.get_item_with_category(item_id)
    if found is None:
        raise InventoryNotFoundError
    item, category = found
    zone = _zone(session, clinic_id)
    today = now.astimezone(zone).date()
    quantities = repository.batch_quantities(item.id)
    batches = [
        _batch_view(batch, today, zone, quantities.get(batch.id, 0))
        for batch in repository.list_batches(item.id)
    ]
    return ItemDetail(
        _item_view(item, category, repository.batch_count(item.id), repository.item_stock(item.id)),
        batches,
    )


def create_item(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    name: str,
    category_id: UUID,
    unit: str,
    low_stock_threshold: int,
) -> ItemView:
    cleaned_name = clean_item_name(name)
    cleaned_unit = clean_unit(unit)
    threshold = check_threshold(low_stock_threshold)
    repository = InventoryRepository(session, clinic_id)
    category = repository.get_category(category_id)
    if category is None:
        raise InventoryNotFoundError
    if repository.find_item_by_name(cleaned_name) is not None:
        raise DuplicateNameError
    item = InventoryItem(
        id=uuid4(),
        category_id=category.id,
        name=cleaned_name,
        unit=cleaned_unit,
        low_stock_threshold=threshold,
        status="active",
    )
    repository.add_item(item)
    record(
        session, clinic_id, actor_user_id, "inventory_item", item.id, "create", changed_fields=[]
    )
    _flush(session, duplicate=DuplicateNameError)
    session.refresh(item)
    return _item_view(item, category, 0, 0)


def edit_item(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    item_id: UUID,
    changes: ItemChanges,
) -> ItemView:
    if not changes.fields:
        raise InventoryFieldError("body", "missing")
    cleaned_name = _required_name(changes)
    cleaned_unit = _required_unit(changes)
    threshold = _required_threshold(changes)
    if "category_id" in changes.fields and changes.category_id is None:
        raise InventoryFieldError("category_id", "missing")
    repository = InventoryRepository(session, clinic_id)
    item = repository.get_item(item_id, lock=True)
    if item is None:
        raise InventoryNotFoundError
    category = repository.get_category(item.category_id)
    if "category_id" in changes.fields:
        found = repository.get_category(changes.category_id) if changes.category_id else None
        if found is None:
            raise InventoryNotFoundError
        category = found
    if category is None:
        raise InventoryNotFoundError
    next_name = item.name if cleaned_name is None else cleaned_name
    taken = repository.find_item_by_name(next_name)
    if taken is not None and taken.id != item.id:
        raise DuplicateNameError
    after = {
        "name": next_name,
        "category_id": category.id,
        "unit": item.unit if cleaned_unit is None else cleaned_unit,
        "low_stock_threshold": item.low_stock_threshold if threshold is None else threshold,
    }
    before = {
        "name": item.name,
        "category_id": item.category_id,
        "unit": item.unit,
        "low_stock_threshold": item.low_stock_threshold,
    }
    changed = changed_field_names(before, after, ITEM_AUDIT_FIELDS)
    item.name = next_name
    item.category_id = category.id
    item.unit = item.unit if cleaned_unit is None else cleaned_unit
    if threshold is not None:
        item.low_stock_threshold = threshold
    if changed:
        record(
            session,
            clinic_id,
            actor_user_id,
            "inventory_item",
            item.id,
            "update",
            changed_fields=changed,
        )
    _flush(session, duplicate=DuplicateNameError)
    session.refresh(item)
    return _item_view(
        item, category, repository.batch_count(item.id), repository.item_stock(item.id)
    )


def set_item_status(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    item_id: UUID,
    status: str,
) -> ItemView:
    checked = check_item_status(status)
    repository = InventoryRepository(session, clinic_id)
    item = repository.get_item(item_id, lock=True)
    if item is None:
        raise InventoryNotFoundError
    if item.status == checked:
        raise InvalidItemStatusError
    item.status = checked
    record(
        session,
        clinic_id,
        actor_user_id,
        "inventory_item",
        item.id,
        "status_change",
        changed_fields=["status"],
    )
    _flush(session, duplicate=DuplicateNameError)
    session.refresh(item)
    category = repository.category_for_item(item)
    if category is None:
        raise InventoryNotFoundError
    return _item_view(
        item, category, repository.batch_count(item.id), repository.item_stock(item.id)
    )


def add_batch(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    item_id: UUID,
    batch_number: str,
    expiry_on: date | None,
    now: datetime,
) -> BatchView:
    cleaned = clean_batch_number(batch_number)
    zone = _zone(session, clinic_id)
    _checked_expiry(expiry_on, zone, now)
    repository = InventoryRepository(session, clinic_id)
    item = repository.get_item(item_id, lock=True)
    if item is None:
        raise InventoryNotFoundError
    if item.status != "active":
        raise ItemInactiveError
    if repository.find_batch_by_number(item.id, cleaned) is not None:
        raise DuplicateBatchError
    batch = InventoryBatch(
        id=uuid4(),
        item_id=item.id,
        batch_number=cleaned,
        expiry_on=expiry_on,
    )
    repository.add_batch(batch)
    record(
        session,
        clinic_id,
        actor_user_id,
        "inventory_batch",
        batch.id,
        "create",
        changed_fields=[],
    )
    _flush(session, duplicate=DuplicateBatchError)
    session.refresh(batch)
    return _batch_view(batch, now.astimezone(zone).date(), zone, 0)


def edit_batch(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    batch_id: UUID,
    changes: BatchChanges,
    now: datetime,
) -> BatchView:
    if not changes.fields:
        raise InventoryFieldError("body", "missing")
    zone = _zone(session, clinic_id)
    cleaned = None
    if "batch_number" in changes.fields:
        if changes.batch_number is None:
            raise InventoryFieldError("batch_number", "missing")
        cleaned = clean_batch_number(changes.batch_number)
    if "expiry_on" in changes.fields:
        _checked_expiry(changes.expiry_on, zone, now)
    repository = InventoryRepository(session, clinic_id)
    batch = repository.get_batch(batch_id, lock=True)
    if batch is None:
        raise InventoryNotFoundError
    next_number = batch.batch_number if cleaned is None else cleaned
    taken = repository.find_batch_by_number(batch.item_id, next_number)
    if taken is not None and taken.id != batch.id:
        raise DuplicateBatchError
    next_expiry = batch.expiry_on if "expiry_on" not in changes.fields else changes.expiry_on
    changed = changed_field_names(
        {"batch_number": batch.batch_number, "expiry_on": batch.expiry_on},
        {"batch_number": next_number, "expiry_on": next_expiry},
        BATCH_AUDIT_FIELDS,
    )
    batch.batch_number = next_number
    batch.expiry_on = next_expiry
    if changed:
        record(
            session,
            clinic_id,
            actor_user_id,
            "inventory_batch",
            batch.id,
            "update",
            changed_fields=changed,
        )
    _flush(session, duplicate=DuplicateBatchError)
    session.refresh(batch)
    return _batch_view(
        batch, now.astimezone(zone).date(), zone, repository.batch_quantity(batch.id)
    )


def restock(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    batch_id: UUID,
    quantity: int,
) -> TransactionView:
    """Add stock to one batch. An inactive item is refused. The batch row is locked."""
    checked = check_restock_quantity(quantity)
    repository = InventoryRepository(session, clinic_id)
    batch = repository.get_batch(batch_id, lock=True)
    if batch is None:
        raise InventoryNotFoundError
    item = repository.get_item(batch.item_id)
    if item is None:
        raise InventoryNotFoundError
    if item.status != "active":
        raise ItemInactiveError
    _refuse_negative_stock(repository, batch.id, checked)
    return _record_transaction(
        session,
        clinic_id,
        actor_user_id,
        repository,
        batch,
        "restock",
        None,
        checked,
    )


def adjust(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    batch_id: UUID,
    quantity_change: int,
    reason: str,
) -> TransactionView:
    """Write off or correct one batch. Allowed on an inactive item. The batch row is locked."""
    checked = check_quantity_change(quantity_change)
    checked_reason = check_adjustment_reason(reason)
    check_adjustment_sign(checked, checked_reason)
    repository = InventoryRepository(session, clinic_id)
    batch = repository.get_batch(batch_id, lock=True)
    if batch is None:
        raise InventoryNotFoundError
    _refuse_negative_stock(repository, batch.id, checked)
    return _record_transaction(
        session,
        clinic_id,
        actor_user_id,
        repository,
        batch,
        "adjustment",
        checked_reason,
        checked,
    )


def list_transactions(
    session: Session,
    clinic_id: UUID,
    item_id: UUID,
    page: int,
    page_size: int,
) -> TransactionPage:
    repository = InventoryRepository(session, clinic_id)
    if repository.get_item(item_id) is None:
        raise InventoryNotFoundError
    zone = _zone(session, clinic_id)
    rows, total = repository.list_transactions(item_id, page, page_size)
    return TransactionPage(
        items=[
            _transaction_view(row, batch_number, recorded_by, zone)
            for row, batch_number, recorded_by in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def _record_transaction(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    repository: InventoryRepository,
    batch: InventoryBatch,
    type_name: str,
    reason: str | None,
    quantity_change: int,
) -> TransactionView:
    transaction = InventoryTransaction(
        id=uuid4(),
        batch_id=batch.id,
        type=type_name,
        reason=reason,
        quantity_change=quantity_change,
        created_by_user_id=actor_user_id,
    )
    repository.add_transaction(transaction)
    record(
        session,
        clinic_id,
        actor_user_id,
        "inventory_transaction",
        transaction.id,
        "create",
        changed_fields=[],
    )
    _flush(session, duplicate=InventoryNotFoundError)
    session.refresh(transaction)
    zone = _zone(session, clinic_id)
    recorded_by = _actor_name(session, clinic_id, actor_user_id)
    return _transaction_view(transaction, batch.batch_number, recorded_by, zone)


def _refuse_negative_stock(repository: InventoryRepository, batch_id: UUID, change: int) -> None:
    """Read the total while the caller holds the batch-row lock."""
    if repository.batch_quantity(batch_id) + change < 0:
        raise InsufficientStockError


def _actor_name(session: Session, clinic_id: UUID, actor_user_id: UUID) -> str:
    user = session.scalars(
        scoped_select(AppUser, clinic_id).where(AppUser.id == actor_user_id)
    ).one_or_none()
    if user is None:
        raise InventoryNotFoundError
    return str(user.full_name)


def _required_name(changes: ItemChanges) -> str | None:
    if "name" not in changes.fields:
        return None
    if changes.name is None:
        raise InventoryFieldError("name", "missing")
    return clean_item_name(changes.name)


def _required_unit(changes: ItemChanges) -> str | None:
    if "unit" not in changes.fields:
        return None
    if changes.unit is None:
        raise InventoryFieldError("unit", "missing")
    return clean_unit(changes.unit)


def _required_threshold(changes: ItemChanges) -> int | None:
    if "low_stock_threshold" not in changes.fields:
        return None
    if changes.low_stock_threshold is None:
        raise InventoryFieldError("low_stock_threshold", "missing")
    return check_threshold(changes.low_stock_threshold)


def _checked_expiry(expiry_on: date | None, zone: ZoneInfo, now: datetime) -> None:
    if expiry_on is None:
        return
    problem = expiry_problem(expiry_on, zone, now)
    if problem is not None:
        raise InventoryFieldError("expiry_on", problem)


def _category_view(repository: InventoryRepository, category: InventoryCategory) -> CategoryView:
    count = 0
    for row, item_count in repository.list_categories():
        if row.id == category.id:
            count = item_count
    return CategoryView(category.id, category.name, count)


def _item_view(
    item: InventoryItem, category: InventoryCategory, batch_count: int, stock: int
) -> ItemView:
    return ItemView(
        id=item.id,
        name=item.name,
        category=CategoryLink(category.id, category.name),
        unit=item.unit,
        low_stock_threshold=item.low_stock_threshold,
        status=item.status,
        batch_count=batch_count,
        stock=stock,
    )


def _batch_view(batch: InventoryBatch, today: date, zone: ZoneInfo, quantity: int) -> BatchView:
    return BatchView(
        id=batch.id,
        batch_number=batch.batch_number,
        expiry_on=batch.expiry_on,
        expired=is_expired(batch.expiry_on, today),
        quantity=quantity,
        created_at=batch.created_at.astimezone(zone),
    )


def _transaction_view(
    transaction: InventoryTransaction,
    batch_number: str,
    recorded_by: str,
    zone: ZoneInfo,
) -> TransactionView:
    return TransactionView(
        id=transaction.id,
        type=transaction.type,
        reason=transaction.reason,
        quantity_change=transaction.quantity_change,
        batch_id=transaction.batch_id,
        batch_number=batch_number,
        recorded_by=recorded_by,
        created_at=transaction.created_at.astimezone(zone),
    )


def _today(session: Session, clinic_id: UUID, now: datetime) -> date:
    return now.astimezone(_zone(session, clinic_id)).date()


def _zone(session: Session, clinic_id: UUID) -> ZoneInfo:
    clinic = ClinicDayRepository(session, clinic_id).get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    try:
        return ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        raise ClinicNotFoundError from None


def _flush(session: Session, *, duplicate: type[Exception]) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        if isinstance(exc.orig, UniqueViolation):
            raise duplicate from None
        if isinstance(exc.orig, ForeignKeyViolation):
            raise InventoryNotFoundError from None
        raise
