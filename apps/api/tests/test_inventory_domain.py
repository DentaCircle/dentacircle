"""Inventory rules that do not touch the database."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from dentacircle.domain.inventory import (
    InventoryFieldError,
    changed_field_names,
    check_item_status,
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
