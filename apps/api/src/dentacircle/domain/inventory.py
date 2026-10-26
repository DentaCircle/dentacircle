"""Inventory setup: names, units, statuses, expiry and stock movements.

A batch is a label and an optional expiry date. It stores no quantity.
Quantity is the sum of append-only transactions. `expired` is calculated
from the clinic-local date. Neither value is stored on the batch.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

MAX_CATEGORY_NAME_LENGTH = 80
MAX_ITEM_NAME_LENGTH = 120
MAX_UNIT_LENGTH = 30
MAX_BATCH_NUMBER_LENGTH = 60
MAX_LOW_STOCK_THRESHOLD = 1_000_000
MAX_QUANTITY_CHANGE = 1_000_000
EARLIEST_EXPIRY = date(2000, 1, 1)
EXPIRY_HORIZON_YEARS = 20
ITEM_STATUSES = ("active", "inactive")
ITEM_LIST_VIEWS = ("active", "inactive", "all")
INVENTORY_WRITE_ROLES = ("inventory_admin", "clinic_admin")
INVENTORY_READ_ROLES = ("inventory_admin", "clinic_admin", "clinician")
TRANSACTION_TYPES = ("restock", "adjustment")
ADJUSTMENT_REASONS = ("damaged", "expired", "correction")
NEGATIVE_ADJUSTMENT_REASONS = ("damaged", "expired")
CATEGORY_AUDIT_FIELDS = ("name",)
ITEM_AUDIT_FIELDS = ("name", "category_id", "unit", "low_stock_threshold")
BATCH_AUDIT_FIELDS = ("batch_number", "expiry_on")


class InventoryFieldError(Exception):
    """One field failed a rule. `code` is a validation name and carries no submitted value."""

    def __init__(self, field: str, code: str) -> None:
        self.field = field
        self.code = code
        super().__init__(code)


def clean_category_name(value: str) -> str:
    return _clean_text(value, "name", MAX_CATEGORY_NAME_LENGTH)


def clean_item_name(value: str) -> str:
    return _clean_text(value, "name", MAX_ITEM_NAME_LENGTH)


def clean_unit(value: str) -> str:
    return _clean_text(value, "unit", MAX_UNIT_LENGTH)


def clean_batch_number(value: str) -> str:
    return _clean_text(value, "batch_number", MAX_BATCH_NUMBER_LENGTH)


def check_threshold(value: int) -> int:
    """A whole number from 0 through 1,000,000. Booleans are refused."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise InventoryFieldError("low_stock_threshold", "int_type")
    if value < 0 or value > MAX_LOW_STOCK_THRESHOLD:
        raise InventoryFieldError("low_stock_threshold", "int_parsing")
    return value


def check_restock_quantity(value: int) -> int:
    """A whole number from 1 through 1,000,000. Booleans are refused."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise InventoryFieldError("quantity", "int_type")
    if value < 1 or value > MAX_QUANTITY_CHANGE:
        raise InventoryFieldError("quantity", "int_parsing")
    return value


def check_quantity_change(value: int) -> int:
    """A non-zero whole number within ±1,000,000. Booleans are refused."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise InventoryFieldError("quantity_change", "int_type")
    if value == 0 or value < -MAX_QUANTITY_CHANGE or value > MAX_QUANTITY_CHANGE:
        raise InventoryFieldError("quantity_change", "int_parsing")
    return value


def check_adjustment_reason(reason: str) -> str:
    if reason not in ADJUSTMENT_REASONS:
        raise InventoryFieldError("reason", "literal_error")
    return reason


def check_adjustment_sign(quantity_change: int, reason: str) -> None:
    """Damaged and expired remove stock. A correction may add or remove it."""
    if reason in NEGATIVE_ADJUSTMENT_REASONS and quantity_change > 0:
        raise InventoryFieldError("quantity_change", "must_be_negative")


def check_item_status(status: str) -> str:
    if status not in ITEM_STATUSES:
        raise InventoryFieldError("status", "literal_error")
    return status


def check_list_view(status: str) -> str:
    if status not in ITEM_LIST_VIEWS:
        raise InventoryFieldError("status", "literal_error")
    return status


def expiry_problem(day: date, zone: ZoneInfo, now: datetime) -> str | None:
    """Why this date is outside 2000-01-01 through 20 years after clinic-today.

    Past dates inside that window are allowed. None when the date is allowed.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    today = now.astimezone(zone).date()
    if day < EARLIEST_EXPIRY:
        return "before_2000"
    if day > _add_years(today, EXPIRY_HORIZON_YEARS):
        return "beyond_horizon"
    return None


def is_expired(expiry_on: date | None, today: date) -> bool:
    """True when the expiry date is before today. A missing date is not expired."""
    return expiry_on is not None and expiry_on < today


def changed_field_names(
    before: dict[str, object], after: dict[str, object], fields: tuple[str, ...]
) -> list[str]:
    """Names whose values differ, in `fields` order. Values are never returned."""
    return [field for field in fields if before[field] != after[field]]


def _clean_text(value: str, field: str, limit: int) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise InventoryFieldError(field, "string_too_short")
    if len(trimmed) > limit:
        raise InventoryFieldError(field, "string_too_long")
    return trimmed


def _add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)
