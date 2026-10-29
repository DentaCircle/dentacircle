"""Inventory rules that do not touch the database."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from dentacircle.domain.inventory import (
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

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 25, 9, 0, tzinfo=_ZONE)
_TODAY = date(2026, 10, 25)


def test_names_units_and_batch_numbers_are_trimmed_to_their_limits() -> None:
    assert clean_category_name("  Consumables  ") == "Consumables"
    assert clean_category_name("c" * 80) == "c" * 80
    assert clean_item_name("  Gloves M  ") == "Gloves M"
    assert clean_item_name("n" * 120) == "n" * 120
    assert clean_unit("  box  ") == "box"
    assert clean_unit("u" * 30) == "u" * 30
    assert clean_batch_number("  LOT-1  ") == "LOT-1"
    assert clean_batch_number("b" * 60) == "b" * 60
    with pytest.raises(InventoryFieldError) as blank:
        clean_category_name("   ")
    assert (blank.value.field, blank.value.code) == ("name", "string_too_short")
    with pytest.raises(InventoryFieldError) as long_name:
        clean_item_name("n" * 121)
    assert (long_name.value.field, long_name.value.code) == ("name", "string_too_long")
    with pytest.raises(InventoryFieldError) as long_unit:
        clean_unit("u" * 31)
    assert long_unit.value.field == "unit"
    with pytest.raises(InventoryFieldError) as long_batch:
        clean_batch_number("b" * 61)
    assert long_batch.value.code == "string_too_long"


@pytest.mark.parametrize("value", [0, 1_000_000])
def test_the_threshold_accepts_the_whole_number_ends(value: int) -> None:
    assert check_threshold(value) == value


@pytest.mark.parametrize("value", [-1, 1_000_001, True])
def test_the_threshold_refuses_out_of_range_and_booleans(value: int) -> None:
    with pytest.raises(InventoryFieldError) as error:
        check_threshold(value)
    assert error.value.field == "low_stock_threshold"


@pytest.mark.parametrize("value", [1, 1_000_000])
def test_a_restock_accepts_the_whole_number_ends(value: int) -> None:
    assert check_restock_quantity(value) == value


@pytest.mark.parametrize("value", [0, -1, 1_000_001, True, False])
def test_a_restock_refuses_zero_decimals_range_and_booleans(value: int) -> None:
    with pytest.raises(InventoryFieldError) as error:
        check_restock_quantity(value)
    assert error.value.field == "quantity"


@pytest.mark.parametrize("value", [-1_000_000, -1, 1, 1_000_000])
def test_an_adjustment_accepts_either_sign_inside_the_limit(value: int) -> None:
    assert check_quantity_change(value) == value


@pytest.mark.parametrize("value", [0, 1_000_001, -1_000_001, True])
def test_an_adjustment_refuses_zero_out_of_range_and_booleans(value: int) -> None:
    with pytest.raises(InventoryFieldError) as error:
        check_quantity_change(value)
    assert error.value.field == "quantity_change"
    assert error.value.code == ("int_type" if value is True else "int_parsing")


@pytest.mark.parametrize("reason", ["damaged", "expired", "correction"])
def test_an_adjustment_reason_is_one_of_three(reason: str) -> None:
    assert check_adjustment_reason(reason) == reason


def test_an_unknown_adjustment_reason_is_refused() -> None:
    with pytest.raises(InventoryFieldError) as error:
        check_adjustment_reason("transfer")
    assert error.value.code == "literal_error"


def test_damaged_and_expired_must_remove_stock_and_a_correction_may_add() -> None:
    check_adjustment_sign(-1, "damaged")
    check_adjustment_sign(-4, "expired")
    check_adjustment_sign(2, "correction")
    check_adjustment_sign(-2, "correction")
    with pytest.raises(InventoryFieldError) as damaged:
        check_adjustment_sign(1, "damaged")
    assert damaged.value.code == "must_be_negative"
    with pytest.raises(InventoryFieldError) as expired:
        check_adjustment_sign(1, "expired")
    assert expired.value.field == "quantity_change"


def test_item_status_is_active_or_inactive() -> None:
    assert check_item_status("active") == "active"
    assert check_item_status("inactive") == "inactive"
    with pytest.raises(InventoryFieldError) as error:
        check_item_status("archived")
    assert error.value.code == "literal_error"


def test_expiry_allows_past_dates_inside_the_window() -> None:
    assert expiry_problem(date(2000, 1, 1), _ZONE, _NOW) is None
    assert expiry_problem(_TODAY, _ZONE, _NOW) is None
    assert expiry_problem(date(1999, 12, 31), _ZONE, _NOW) == "before_2000"
    assert expiry_problem(date(2046, 10, 25), _ZONE, _NOW) is None
    assert expiry_problem(date(2046, 10, 26), _ZONE, _NOW) == "beyond_horizon"


def test_a_batch_is_expired_only_when_its_date_is_before_today() -> None:
    assert is_expired(date(2026, 10, 24), _TODAY) is True
    assert is_expired(_TODAY, _TODAY) is False
    assert is_expired(None, _TODAY) is False


def test_changed_field_names_keep_order_and_drop_values() -> None:
    changed = changed_field_names(
        {"name": "Gloves", "unit": "box"},
        {"name": "Gloves M", "unit": "box"},
        ("unit", "name"),
    )
    assert changed == ["name"]
    assert "Gloves" not in changed


def test_inventory_alert_boundaries() -> None:
    from datetime import date, timedelta

    from dentacircle.domain.inventory import inventory_alerts, is_expiring_soon

    today = date(2026, 10, 29)
    assert inventory_alerts(True, 0, 0, True, True) == ["out_of_stock", "expired", "expiring_soon"]
    assert inventory_alerts(True, 3, 3, False, False) == ["low_stock"]
    assert inventory_alerts(True, 4, 3, False, False) == []
    assert inventory_alerts(True, 1, 0, False, False) == []
    assert inventory_alerts(False, 0, 3, True, True) == []
    assert not is_expiring_soon(today - timedelta(days=1), 1, today)
    assert is_expiring_soon(today, 1, today)
    assert is_expiring_soon(today + timedelta(days=30), 1, today)
    assert not is_expiring_soon(today + timedelta(days=31), 1, today)
    assert not is_expiring_soon(today, 0, today)
    assert not is_expiring_soon(None, 1, today)
