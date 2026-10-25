"""Inventory routes: roles, check order, tenancy, filters, paging and no echo."""

import logging
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.inventory import INVENTORY_READ_ROLES, INVENTORY_WRITE_ROLES
from dentacircle.main import create_app
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes, unmarked_routes
from tests.test_timeline_routes import _route_roles

_ZONE = ZoneInfo("Asia/Kolkata")
_MARKER = "distinctive-glove-marker"
_READ_ROUTES = {
    ("GET", "/inventory/categories"),
    ("GET", "/inventory/items"),
    ("GET", "/inventory/items/{item_id}"),
    ("GET", "/inventory/items/{item_id}/transactions"),
}
_WRITE_ROUTES = {
    ("POST", "/inventory/categories"),
    ("PATCH", "/inventory/categories/{category_id}"),
    ("POST", "/inventory/items"),
    ("PATCH", "/inventory/items/{item_id}"),
    ("POST", "/inventory/items/{item_id}/status"),
    ("POST", "/inventory/items/{item_id}/batches"),
    ("PATCH", "/inventory/batches/{batch_id}"),
    ("POST", "/inventory/batches/{batch_id}/restock"),
    ("POST", "/inventory/batches/{batch_id}/adjustments"),
}


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_create_category_and_item_return_the_setup_shape(api: TestClient) -> None:
    cookies = _cookie(api, "inventory@x.test")
    category = api.post("/inventory/categories", cookies=cookies, json={"name": "  Consumables  "})
    assert category.status_code == 201
    assert set(category.json()) == {"id", "name", "item_count"}
    assert category.json()["name"] == "Consumables"
    assert category.json()["item_count"] == 0
    item = api.post(
        "/inventory/items",
        cookies=cookies,
        json={
            "name": f"  {_MARKER}  ",
            "category_id": category.json()["id"],
            "unit": "  box  ",
            "low_stock_threshold": 2,
        },
    )
    assert item.status_code == 201
    body = item.json()
    assert set(body) == {
        "id",
        "name",
        "category",
        "unit",
        "low_stock_threshold",
        "status",
        "batch_count",
        "stock",
    }
    assert body["name"] == _MARKER
    assert body["status"] == "active"
    assert body["unit"] == "box"
    assert body["batch_count"] == 0
    assert body["stock"] == 0
    assert body["category"]["name"] == "Consumables"
    assert "quantity" not in body


def test_checks_run_in_order(api: TestClient) -> None:
    missing = str(uuid4())
    bad = {"name": " ", "category_id": missing, "unit": " ", "note": _MARKER}
    anonymous = api.post("/inventory/items", json=bad)
    assert anonymous.status_code == 401
    denied = api.post("/inventory/items", cookies=_cookie(api, "clinician@x.test"), json=bad)
    assert denied.status_code == 403
    cookies = _cookie(api, "admin@x.test")
    invalid = api.post(
        "/inventory/items",
        cookies=cookies,
        json={"name": " ", "category_id": missing, "unit": "box"},
    )
    assert invalid.status_code == 422
    absent = api.post(
        "/inventory/items",
        cookies=cookies,
        json={"name": "Gloves", "category_id": missing, "unit": "box"},
    )
    assert absent.status_code == 404
    category_id = _category(api)
    first = api.post(
        "/inventory/items",
        cookies=cookies,
        json={"name": "Gloves", "category_id": category_id, "unit": "box"},
    )
    assert first.status_code == 201
    duplicate = api.post(
        "/inventory/items",
        cookies=cookies,
        json={"name": "gloves", "category_id": category_id, "unit": "box"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_name"


def test_status_and_batch_checks_run_in_order(api: TestClient) -> None:
    missing = str(uuid4())
    anonymous = api.post(f"/inventory/items/{missing}/status", json={"status": "nope"})
    assert anonymous.status_code == 401
    cookies = _cookie(api, "inventory@x.test")
    denied = api.post(
        f"/inventory/items/{missing}/batches",
        cookies=_cookie(api),
        json={"batch_number": " "},
    )
    assert denied.status_code == 403
    invalid = api.post(
        f"/inventory/items/{missing}/status", cookies=cookies, json={"status": "archived"}
    )
    assert invalid.status_code == 422
    absent = api.post(
        f"/inventory/items/{missing}/status", cookies=cookies, json={"status": "inactive"}
    )
    assert absent.status_code == 404
    item_id = _item(api, cookies)
    repeat = api.post(
        f"/inventory/items/{item_id}/status", cookies=cookies, json={"status": "active"}
    )
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "invalid_status"
    early = api.post(
        f"/inventory/items/{missing}/batches",
        cookies=cookies,
        json={"batch_number": "LOT", "expiry_on": "1999-12-31"},
    )
    assert early.status_code == 422
    missing_item = api.post(
        f"/inventory/items/{missing}/batches", cookies=cookies, json={"batch_number": "LOT"}
    )
    assert missing_item.status_code == 404
    api.post(f"/inventory/items/{item_id}/status", cookies=cookies, json={"status": "inactive"})
    inactive = api.post(
        f"/inventory/items/{item_id}/batches", cookies=cookies, json={"batch_number": "LOT-1"}
    )
    assert inactive.status_code == 409
    assert inactive.json()["error"]["code"] == "item_inactive"
    api.post(f"/inventory/items/{item_id}/status", cookies=cookies, json={"status": "active"})
    added = api.post(
        f"/inventory/items/{item_id}/batches", cookies=cookies, json={"batch_number": "LOT-1"}
    )
    assert added.status_code == 201
    duplicate = api.post(
        f"/inventory/items/{item_id}/batches", cookies=cookies, json={"batch_number": "lot-1"}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_batch"


def test_the_list_filters_pages_and_an_unknown_category_is_empty(api: TestClient) -> None:
    cookies = _cookie(api, "inventory@x.test")
    consumables = _category(api, "Consumables")
    medicines = _category(api, "Medicines")
    gloves = _item(api, cookies, "Gloves M", consumables, "box")
    _item(api, cookies, "Medicine A", medicines, "tablets")
    api.post(f"/inventory/items/{gloves}/status", cookies=cookies, json={"status": "inactive"})
    active = api.get("/inventory/items", cookies=cookies)
    assert active.status_code == 200
    assert active.json()["total"] == 1
    assert active.json()["items"][0]["name"] == "Medicine A"
    found = api.get(
        "/inventory/items",
        cookies=cookies,
        params={"status": "all", "q": "glove", "category_id": consumables, "page_size": 1},
    )
    assert found.json()["total"] == 1
    assert found.json()["items"][0]["batch_count"] == 0
    empty = api.get("/inventory/items", cookies=cookies, params={"category_id": str(uuid4())})
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    for params in ({"page": 0}, {"page_size": 0}, {"page_size": 101}, {"status": "archived"}):
        refused = api.get("/inventory/items", cookies=cookies, params=params)
        assert refused.status_code == 422
    page = api.get(
        "/inventory/items", cookies=cookies, params={"status": "all", "page": 2, "page_size": 1}
    )
    assert page.json()["items"][0]["name"] == "Medicine A"
    assert set(page.json()) == {"items", "total", "page", "page_size"}


def test_one_item_lists_batches_with_expiry_and_hides_stock_fields(api: TestClient) -> None:
    cookies = _cookie(api, "admin@x.test")
    item_id = _item(api, cookies)
    past = (_today() - timedelta(days=1)).isoformat()
    future = (_today() + timedelta(days=30)).isoformat()
    api.post(
        f"/inventory/items/{item_id}/batches",
        cookies=cookies,
        json={"batch_number": "LATER", "expiry_on": future},
    )
    api.post(f"/inventory/items/{item_id}/batches", cookies=cookies, json={"batch_number": "NONE"})
    api.post(
        f"/inventory/items/{item_id}/batches",
        cookies=cookies,
        json={"batch_number": "EARLY", "expiry_on": past},
    )
    response = api.get(f"/inventory/items/{item_id}", cookies=cookies)
    assert response.status_code == 200
    body = response.json()
    assert [batch["batch_number"] for batch in body["batches"]] == ["EARLY", "LATER", "NONE"]
    assert body["batches"][0]["expired"] is True
    assert body["batches"][1]["expired"] is False
    assert body["batches"][2]["expiry_on"] is None
    assert body["stock"] == 0
    assert [batch["quantity"] for batch in body["batches"]] == [0, 0, 0]
    assert "supplier" not in response.text
    empty = api.patch(f"/inventory/items/{item_id}", cookies=cookies, json={})
    assert empty.status_code == 422
    category_id = _category_of(body)
    same = api.patch(
        f"/inventory/categories/{category_id}", cookies=cookies, json={"name": "Consumables"}
    )
    assert same.status_code == 200


def test_errors_do_not_echo_names_units_batch_numbers_or_ids(
    api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    cookies = _cookie(api, "inventory@x.test")
    category_id = _category(api)
    item_id = _item(api, cookies, _MARKER, category_id, _MARKER)
    missing = str(uuid4())
    with caplog.at_level(logging.DEBUG):
        missing_item = api.get(f"/inventory/items/{missing}", cookies=cookies)
        duplicate = api.post(
            "/inventory/items",
            cookies=cookies,
            json={"name": _MARKER, "category_id": category_id, "unit": _MARKER},
        )
        invalid = api.post(
            f"/inventory/items/{item_id}/batches",
            cookies=cookies,
            json={"batch_number": _MARKER, "expiry_on": "yesterday"},
        )
        batch = api.post(
            f"/inventory/items/{item_id}/batches",
            cookies=cookies,
            json={"batch_number": _MARKER},
        )
        assert batch.status_code == 201
        again = api.post(
            f"/inventory/items/{item_id}/batches",
            cookies=cookies,
            json={"batch_number": _MARKER},
        )
    assert missing_item.status_code == 404
    assert duplicate.status_code == 409
    assert invalid.status_code == 422
    assert again.status_code == 409
    for response in (missing_item, duplicate, invalid, again):
        assert _MARKER not in response.text
        assert item_id not in response.text
        assert missing not in response.text
    log = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("dentacircle")
    )
    assert _MARKER not in log
    posted = "\n".join(line for line in log.splitlines() if "method=POST" in line)
    assert missing not in posted


def test_another_clinic_gets_404_and_may_reuse_the_name(api: TestClient) -> None:
    cookies = _cookie(api, "inventory@x.test")
    category_id = _category(api, "Consumables")
    item_id = _item(api, cookies, _MARKER, category_id, "box")
    batch = api.post(
        f"/inventory/items/{item_id}/batches", cookies=cookies, json={"batch_number": "LOT-1"}
    )
    assert batch.status_code == 201
    _other_clinic()
    other = _cookie(api, "other@x.test")
    stolen = api.get(f"/inventory/items/{item_id}", cookies=other)
    assert stolen.status_code == 404
    assert _MARKER not in stolen.text
    renamed = api.patch(
        f"/inventory/batches/{batch.json()['id']}",
        cookies=other,
        json={"batch_number": "LOT-2"},
    )
    assert renamed.status_code == 404
    copied = api.post("/inventory/categories", cookies=other, json={"name": "Consumables"})
    assert copied.status_code == 201


def test_a_clinician_can_read_and_a_receptionist_cannot(api: TestClient) -> None:
    anonymous = api.post(
        f"/inventory/batches/{uuid4()}/adjustments",
        json={"quantity_change": -1, "reason": "damaged"},
    )
    assert anonymous.status_code == 401
    cookies = _cookie(api, "inventory@x.test")
    category_id = _category(api)
    item_id = _item(api, cookies, "Gloves M", category_id, "box")
    clinician = _cookie(api, "clinician@x.test")
    assert api.get("/inventory/items", cookies=clinician).status_code == 200
    assert api.get(f"/inventory/items/{item_id}", cookies=clinician).status_code == 200
    history = api.get(f"/inventory/items/{item_id}/transactions", cookies=clinician)
    assert history.status_code == 200
    refused = api.post("/inventory/categories", cookies=clinician, json={"name": "X"})
    assert refused.status_code == 403
    restock_denied = api.post(
        f"/inventory/batches/{uuid4()}/restock", cookies=clinician, json={"quantity": 1}
    )
    assert restock_denied.status_code == 403
    desk = _cookie(api)
    assert api.get("/inventory/categories", cookies=desk).status_code == 403
    assert api.get("/inventory/items", cookies=desk).status_code == 403
    assert api.get(f"/inventory/items/{item_id}/transactions", cookies=desk).status_code == 403


def test_every_inventory_route_names_its_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    application = create_app()
    assert unmarked_routes(application) == []
    found = _route_roles(application)
    inventory = {key for key in found if key[1].startswith("/inventory")}
    assert inventory == _READ_ROUTES | _WRITE_ROUTES
    assert all(found[key] == set(INVENTORY_READ_ROLES) for key in _READ_ROUTES)
    assert all(found[key] == set(INVENTORY_WRITE_ROLES) for key in _WRITE_ROUTES)
    allowed = set().union(*(found[key] for key in inventory))
    assert "receptionist" not in allowed
    assert len(list(iter_api_routes(application))) > 0


def test_restock_adjustment_and_history_follow_the_check_order(api: TestClient) -> None:
    missing = str(uuid4())
    anonymous = api.post(f"/inventory/batches/{missing}/restock", json={"quantity": True})
    assert anonymous.status_code == 401
    denied = api.post(
        f"/inventory/batches/{missing}/restock",
        cookies=_cookie(api),
        json={"quantity": True},
    )
    assert denied.status_code == 403
    cookies = _cookie(api, "inventory@x.test")
    for payload in ({"quantity": True}, {"quantity": "4"}, {"quantity": 1.5}, {"quantity": 0}):
        invalid = api.post(f"/inventory/batches/{missing}/restock", cookies=cookies, json=payload)
        assert invalid.status_code == 422
    positive = api.post(
        f"/inventory/batches/{missing}/adjustments",
        cookies=cookies,
        json={"quantity_change": 1, "reason": "damaged"},
    )
    assert positive.status_code == 422
    assert positive.json()["error"]["code"] == "validation_error"
    absent = api.post(
        f"/inventory/batches/{missing}/restock", cookies=cookies, json={"quantity": 1}
    )
    assert absent.status_code == 404
    item_id = _item(api, cookies)
    batch_id = _batch(api, cookies, item_id, "LOT-1")
    api.post(f"/inventory/items/{item_id}/status", cookies=cookies, json={"status": "inactive"})
    inactive = api.post(
        f"/inventory/batches/{batch_id}/restock", cookies=cookies, json={"quantity": 1}
    )
    assert inactive.status_code == 409
    assert inactive.json()["error"]["code"] == "item_inactive"
    written = api.post(
        f"/inventory/batches/{batch_id}/adjustments",
        cookies=cookies,
        json={"quantity_change": -1, "reason": "damaged"},
    )
    assert written.status_code == 409
    assert written.json()["error"]["code"] == "insufficient_stock"
    api.post(f"/inventory/items/{item_id}/status", cookies=cookies, json={"status": "active"})
    added = api.post(
        f"/inventory/batches/{batch_id}/restock", cookies=cookies, json={"quantity": 5}
    )
    assert added.status_code == 201
    assert added.json()["type"] == "restock"
    assert added.json()["reason"] is None
    assert added.json()["quantity_change"] == 5
    assert added.json()["recorded_by"] == "Synthetic Person"
    assert added.json()["created_at"].endswith("+05:30")
    short = api.post(
        f"/inventory/batches/{batch_id}/adjustments",
        cookies=cookies,
        json={"quantity_change": -6, "reason": "expired"},
    )
    assert short.status_code == 409
    assert short.json()["error"]["code"] == "insufficient_stock"
    changed = api.post(
        f"/inventory/batches/{batch_id}/adjustments",
        cookies=cookies,
        json={"quantity_change": -2, "reason": "correction"},
    )
    assert changed.status_code == 201
    assert changed.json()["type"] == "adjustment"
    detail = api.get(f"/inventory/items/{item_id}", cookies=cookies)
    assert detail.json()["stock"] == 3
    assert detail.json()["batches"][0]["quantity"] == 3
    history = api.get(
        f"/inventory/items/{item_id}/transactions",
        cookies=cookies,
        params={"page_size": 1},
    )
    assert history.status_code == 200
    assert set(history.json()) == {"items", "total", "page", "page_size"}
    assert history.json()["total"] == 2
    assert history.json()["items"][0]["quantity_change"] == -2
    assert history.json()["items"][0]["batch"]["batch_number"] == "LOT-1"
    older = api.get(
        f"/inventory/items/{item_id}/transactions",
        cookies=cookies,
        params={"page": 2, "page_size": 1},
    )
    assert older.json()["items"][0]["type"] == "restock"
    empty_item = _item(api, cookies, "Mask", _category(api, "Medicines"), "box")
    empty = api.get(f"/inventory/items/{empty_item}/transactions", cookies=cookies)
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    for params in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        refused = api.get(
            f"/inventory/items/{item_id}/transactions", cookies=cookies, params=params
        )
        assert refused.status_code == 422


def test_stock_errors_do_not_echo_quantity_batch_number_or_ids(
    api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    cookies = _cookie(api, "inventory@x.test")
    item_id = _item(api, cookies, "Gloves M")
    batch_id = _batch(api, cookies, item_id, _MARKER)
    api.post(f"/inventory/batches/{batch_id}/restock", cookies=cookies, json={"quantity": 1})
    missing = str(uuid4())
    with caplog.at_level(logging.DEBUG):
        missing_batch = api.post(
            f"/inventory/batches/{missing}/restock", cookies=cookies, json={"quantity": 424242}
        )
        invalid = api.post(
            f"/inventory/batches/{batch_id}/adjustments",
            cookies=cookies,
            json={"quantity_change": "424242", "reason": "damaged"},
        )
        short = api.post(
            f"/inventory/batches/{batch_id}/adjustments",
            cookies=cookies,
            json={"quantity_change": -424242, "reason": "expired"},
        )
    assert missing_batch.status_code == 404
    assert invalid.status_code == 422
    assert short.status_code == 409
    for response in (missing_batch, invalid, short):
        assert "424242" not in response.text
        assert _MARKER not in response.text
        assert batch_id not in response.text
        assert missing not in response.text
        assert item_id not in response.text
    log = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("dentacircle")
    )
    assert "424242" not in log
    assert _MARKER not in log


def test_another_clinic_cannot_restock_or_read_history(api: TestClient) -> None:
    cookies = _cookie(api, "inventory@x.test")
    item_id = _item(api, cookies, _MARKER)
    batch_id = _batch(api, cookies, item_id, "LOT-1")
    api.post(f"/inventory/batches/{batch_id}/restock", cookies=cookies, json={"quantity": 2})
    _other_clinic()
    other = _cookie(api, "other@x.test")
    stolen = api.post(
        f"/inventory/batches/{batch_id}/restock", cookies=other, json={"quantity": 1}
    )
    history = api.get(f"/inventory/items/{item_id}/transactions", cookies=other)
    assert stolen.status_code == 404
    assert history.status_code == 404
    assert _MARKER not in stolen.text
    assert _MARKER not in history.text
    assert batch_id not in stolen.text
    assert item_id not in history.text


def test_an_expired_batch_still_counts_in_item_stock(api: TestClient) -> None:
    cookies = _cookie(api, "admin@x.test")
    item_id = _item(api, cookies)
    past = (_today() - timedelta(days=2)).isoformat()
    batch = api.post(
        f"/inventory/items/{item_id}/batches",
        cookies=cookies,
        json={"batch_number": "OLD", "expiry_on": past},
    )
    assert batch.status_code == 201
    added = api.post(
        f"/inventory/batches/{batch.json()['id']}/restock",
        cookies=cookies,
        json={"quantity": 8},
    )
    assert added.status_code == 201
    detail = api.get(f"/inventory/items/{item_id}", cookies=cookies)
    assert detail.json()["batches"][0]["expired"] is True
    assert detail.json()["batches"][0]["quantity"] == 8
    assert detail.json()["stock"] == 8
    listed = api.get("/inventory/items", cookies=cookies)
    assert listed.json()["items"][0]["stock"] == 8


def _batch(api: TestClient, cookies: dict[str, str], item_id: str, batch_number: str) -> str:
    response = api.post(
        f"/inventory/items/{item_id}/batches",
        cookies=cookies,
        json={"batch_number": batch_number},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _category(api: TestClient, name: str = "Consumables") -> str:
    response = api.post(
        "/inventory/categories", cookies=_cookie(api, "admin@x.test"), json={"name": name}
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _item(
    api: TestClient,
    cookies: dict[str, str],
    name: str = "Gloves M",
    category_id: str | None = None,
    unit: str = "box",
) -> str:
    if category_id is None:
        category_id = _category(api)
    response = api.post(
        "/inventory/items",
        cookies=cookies,
        json={"name": name, "category_id": category_id, "unit": unit},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _category_of(body: dict[str, object]) -> str:
    category = body["category"]
    assert isinstance(category, dict)
    return str(category["id"])


def _today() -> date:
    return datetime.now(_ZONE).date()


def _other_clinic() -> None:
    from dentacircle.services.provisioning_service import create_user, get_or_create_clinic

    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Another Synthetic Clinic")
        create_user(
            session,
            clinic.id,
            "other@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["inventory_admin"],
        )
        session.commit()
