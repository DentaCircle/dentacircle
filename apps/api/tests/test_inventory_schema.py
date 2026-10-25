"""Inventory tables: lengths, status, uniqueness, tenancy keys, and no quantity."""

from uuid import uuid4

import psycopg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import to_psycopg_url
from tests.test_migrations import _config, _public_tables, _version

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_CATEGORY = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_OTHER_CATEGORY = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_ITEM = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_USER = "dddddddd-dddd-dddd-dddd-dddddddddddd"
_OTHER_USER = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
_BATCH = "ffffffff-ffff-ffff-ffff-ffffffffffff"

_CATEGORY_COLUMNS = {"id", "clinic_id", "name", "created_at"}
_ITEM_COLUMNS = {
    "id",
    "clinic_id",
    "category_id",
    "name",
    "unit",
    "low_stock_threshold",
    "status",
    "created_at",
}
_BATCH_COLUMNS = {"id", "clinic_id", "item_id", "batch_number", "expiry_on", "created_at"}
_TRANSACTION_COLUMNS = {
    "id",
    "clinic_id",
    "batch_id",
    "type",
    "reason",
    "quantity_change",
    "created_by_user_id",
    "created_at",
}
_FORBIDDEN = {"quantity", "cost", "supplier", "purchase_cost", "on_hand"}


@pytest.fixture
def migrated(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    return throwaway_database_url


def test_upgrade_downgrade_upgrade(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = _config()
    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0019_inventory_transactions"
    tables = _public_tables(throwaway_database_url)
    assert "inventory_category" in tables
    assert "inventory_item" in tables
    assert "inventory_batch" in tables
    assert "inventory_transaction" in tables
    assert _columns(throwaway_database_url, "inventory_category") == _CATEGORY_COLUMNS
    assert _columns(throwaway_database_url, "inventory_item") == _ITEM_COLUMNS
    assert _columns(throwaway_database_url, "inventory_batch") == _BATCH_COLUMNS
    assert _FORBIDDEN.isdisjoint(_ITEM_COLUMNS | _BATCH_COLUMNS | _CATEGORY_COLUMNS)

    command.downgrade(config, "0017_lab_work")
    assert _version(throwaway_database_url) == "0017_lab_work"
    gone = _public_tables(throwaway_database_url)
    assert "inventory_category" not in gone
    assert "inventory_item" not in gone
    assert "inventory_batch" not in gone
    assert "lab_work" in gone

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0019_inventory_transactions"
    assert "inventory_item" in _public_tables(throwaway_database_url)
    assert "inventory_transaction" in _public_tables(throwaway_database_url)


def test_the_same_name_in_two_clinics_is_allowed_and_one_clinic_cannot_repeat_it(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert_category(db_session, _CLINIC, _CATEGORY, "Consumables")
    _insert_category(db_session, _OTHER, _OTHER_CATEGORY, "Consumables")
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_category(db_session, _CLINIC, str(uuid4()), "consumables")


@pytest.mark.parametrize("name", ["", "n" * 81])
def test_a_category_name_must_be_one_to_eighty_characters(
    migrated: str, db_session: Session, name: str
) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_category(db_session, _CLINIC, str(uuid4()), name)


def test_an_item_name_is_unique_per_clinic_ignoring_case(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert_category(db_session, _CLINIC, _CATEGORY, "Consumables")
    _insert_category(db_session, _OTHER, _OTHER_CATEGORY, "Medicines")
    _insert_item(db_session, _CLINIC, _CATEGORY, _ITEM, "Gloves M")
    _insert_item(db_session, _OTHER, _OTHER_CATEGORY, str(uuid4()), "Gloves M")
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_item(db_session, _CLINIC, _CATEGORY, str(uuid4()), "gloves m")


@pytest.mark.parametrize(
    "column,value",
    [
        ("name", ""),
        ("name", "n" * 121),
        ("unit", ""),
        ("unit", "u" * 31),
        ("status", "archived"),
        ("low_stock_threshold", -1),
        ("low_stock_threshold", 1_000_001),
    ],
)
def test_item_checks_reject_bad_lengths_status_and_threshold(
    migrated: str, db_session: Session, column: str, value: object
) -> None:
    _seed(db_session)
    _insert_category(db_session, _CLINIC, _CATEGORY, "Consumables")
    db_session.commit()
    with pytest.raises(IntegrityError):
        name = str(value) if column == "name" else "Gloves"
        extra = {} if column == "name" else {column: value}
        _insert_item(db_session, _CLINIC, _CATEGORY, str(uuid4()), name, **extra)


def test_an_item_cannot_point_at_another_clinics_category(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert_category(db_session, _OTHER, _OTHER_CATEGORY, "Medicines")
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_item(db_session, _CLINIC, _OTHER_CATEGORY, str(uuid4()), "Gloves")


def test_a_batch_number_is_unique_per_item_ignoring_case(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert_category(db_session, _CLINIC, _CATEGORY, "Consumables")
    _insert_item(db_session, _CLINIC, _CATEGORY, _ITEM, "Gloves M")
    other_item = str(uuid4())
    _insert_item(db_session, _CLINIC, _CATEGORY, other_item, "Gloves L")
    _insert_batch(db_session, _CLINIC, _ITEM, "LOT-1")
    _insert_batch(db_session, _CLINIC, other_item, "LOT-1")
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_batch(db_session, _CLINIC, _ITEM, "lot-1")


@pytest.mark.parametrize("batch_number", ["", "b" * 61])
def test_a_batch_number_must_be_one_to_sixty_characters(
    migrated: str, db_session: Session, batch_number: str
) -> None:
    _seed(db_session)
    _insert_category(db_session, _CLINIC, _CATEGORY, "Consumables")
    _insert_item(db_session, _CLINIC, _CATEGORY, _ITEM, "Gloves M")
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_batch(db_session, _CLINIC, _ITEM, batch_number)


def test_an_expiry_before_2000_is_rejected_and_a_blank_expiry_is_allowed(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert_category(db_session, _CLINIC, _CATEGORY, "Consumables")
    _insert_item(db_session, _CLINIC, _CATEGORY, _ITEM, "Gloves M")
    _insert_batch(db_session, _CLINIC, _ITEM, "LOT-1", expiry_on=None)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_batch(db_session, _CLINIC, _ITEM, "LOT-2", expiry_on="1999-12-31")


def test_transactions_upgrade_then_down_to_batches_then_up_again(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = _config()
    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0019_inventory_transactions"
    assert _columns(throwaway_database_url, "inventory_transaction") == _TRANSACTION_COLUMNS
    assert "item_id" not in _TRANSACTION_COLUMNS
    assert _columns(throwaway_database_url, "inventory_batch") == _BATCH_COLUMNS

    command.downgrade(config, "0018_inventory")
    assert _version(throwaway_database_url) == "0018_inventory"
    gone = _public_tables(throwaway_database_url)
    assert "inventory_transaction" not in gone
    assert "inventory_batch" in gone
    assert _function_exists(throwaway_database_url) is False

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0019_inventory_transactions"
    assert "inventory_transaction" in _public_tables(throwaway_database_url)
    assert _function_exists(throwaway_database_url) is True


@pytest.mark.parametrize(
    "type_name,reason,quantity",
    [
        ("consumption", None, 1),
        ("restock", None, 0),
        ("restock", None, 1_000_001),
        ("restock", None, -1),
        ("restock", "correction", 1),
        ("adjustment", None, -1),
        ("adjustment", "lost", -1),
        ("adjustment", "damaged", 1),
        ("adjustment", "expired", 4),
        ("adjustment", "correction", 1_000_001),
        ("adjustment", "correction", -1_000_001),
    ],
)
def test_transaction_checks_reject_a_bad_type_reason_or_quantity(
    migrated: str, db_session: Session, type_name: str, reason: str | None, quantity: int
) -> None:
    _ready_batch(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_transaction(db_session, _CLINIC, _BATCH, _USER, type_name, reason, quantity)


def test_a_transaction_cannot_point_at_another_clinics_batch(
    migrated: str, db_session: Session
) -> None:
    _ready_batch(db_session)
    _insert_user(db_session, _OTHER, _OTHER_USER, "other-transaction@x.test")
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_transaction(db_session, _OTHER, _BATCH, _OTHER_USER, "restock", None, 1)


def test_the_trigger_refuses_update_and_delete(migrated: str, db_session: Session) -> None:
    _ready_batch(db_session)
    _insert_transaction(db_session, _CLINIC, _BATCH, _USER, "restock", None, 5)
    _insert_transaction(db_session, _CLINIC, _BATCH, _USER, "adjustment", "correction", -1)
    db_session.commit()
    with pytest.raises(DBAPIError) as updated:
        db_session.execute(text("UPDATE inventory_transaction SET quantity_change = 9"))
        db_session.flush()
    assert "append-only" in str(updated.value)
    db_session.rollback()
    with pytest.raises(DBAPIError) as deleted:
        db_session.execute(text("DELETE FROM inventory_transaction"))
        db_session.flush()
    assert "append-only" in str(deleted.value)
    db_session.rollback()
    remaining = db_session.scalar(text("SELECT count(*) FROM inventory_transaction"))
    assert int(remaining or 0) == 2


def test_a_batch_cannot_point_at_another_clinics_item(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    _insert_category(db_session, _OTHER, _OTHER_CATEGORY, "Medicines")
    _insert_item(db_session, _OTHER, _OTHER_CATEGORY, _ITEM, "Medicine A")
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_batch(db_session, _CLINIC, _ITEM, "LOT-1")


def _columns(database_url: str, table: str) -> set[str]:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def _seed(session: Session) -> None:
    for clinic_id in (_CLINIC, _OTHER):
        session.execute(
            text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
            {"id": clinic_id},
        )


def _insert_category(session: Session, clinic_id: str, category_id: str, name: str) -> None:
    session.execute(
        text(
            "INSERT INTO inventory_category (id, clinic_id, name) VALUES (:id, :clinic_id, :name)"
        ),
        {"id": category_id, "clinic_id": clinic_id, "name": name},
    )


def _insert_item(
    session: Session,
    clinic_id: str,
    category_id: str,
    item_id: str,
    name: str = "Gloves",
    **overrides: object,
) -> None:
    values = {
        "id": item_id,
        "clinic_id": clinic_id,
        "category_id": category_id,
        "name": name,
        "unit": "box",
        "low_stock_threshold": 0,
        "status": "active",
    }
    values.update(overrides)
    session.execute(
        text(
            "INSERT INTO inventory_item"
            " (id, clinic_id, category_id, name, unit, low_stock_threshold, status)"
            " VALUES (:id, :clinic_id, :category_id, :name, :unit,"
            " :low_stock_threshold, :status)"
        ),
        values,
    )


def _function_exists(database_url: str) -> bool:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT 1 FROM pg_proc WHERE proname = 'inventory_transaction_refuse_change'"
        ).fetchone()
    return row is not None


def _ready_batch(session: Session) -> None:
    _seed(session)
    _insert_user(session, _CLINIC, _USER, "stores@x.test")
    _insert_category(session, _CLINIC, _CATEGORY, "Consumables")
    _insert_item(session, _CLINIC, _CATEGORY, _ITEM, "Gloves M")
    _insert_batch(session, _CLINIC, _ITEM, "LOT-1", batch_id=_BATCH)


def _insert_user(session: Session, clinic_id: str, user_id: str, email: str) -> None:
    session.execute(
        text(
            "INSERT INTO app_user (id, clinic_id, email, full_name, password_hash)"
            " VALUES (:id, :clinic_id, :email, 'Synthetic Stores', 'synthetic-password-marker')"
        ),
        {"id": user_id, "clinic_id": clinic_id, "email": email},
    )


def _insert_transaction(
    session: Session,
    clinic_id: str,
    batch_id: str,
    user_id: str,
    type_name: str,
    reason: str | None,
    quantity_change: int,
) -> None:
    session.execute(
        text(
            "INSERT INTO inventory_transaction"
            " (id, clinic_id, batch_id, type, reason, quantity_change, created_by_user_id)"
            " VALUES (:id, :clinic_id, :batch_id, :type, :reason, :quantity_change,"
            " :created_by_user_id)"
        ),
        {
            "id": str(uuid4()),
            "clinic_id": clinic_id,
            "batch_id": batch_id,
            "type": type_name,
            "reason": reason,
            "quantity_change": quantity_change,
            "created_by_user_id": user_id,
        },
    )


def _insert_batch(
    session: Session,
    clinic_id: str,
    item_id: str,
    batch_number: str,
    expiry_on: str | None = "2026-01-01",
    batch_id: str | None = None,
) -> None:
    session.execute(
        text(
            "INSERT INTO inventory_batch"
            " (id, clinic_id, item_id, batch_number, expiry_on)"
            " VALUES (:id, :clinic_id, :item_id, :batch_number, :expiry_on)"
        ),
        {
            "id": batch_id or str(uuid4()),
            "clinic_id": clinic_id,
            "item_id": item_id,
            "batch_number": batch_number,
            "expiry_on": expiry_on,
        },
    )
