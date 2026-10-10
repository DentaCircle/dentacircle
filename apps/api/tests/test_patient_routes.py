"""Create and list patients over HTTP."""

from collections.abc import Iterator, Mapping
from datetime import datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.patient import PATIENT_ROLES
from dentacircle.main import create_app
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.patient import Patient
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes

_PHONE = "9000000001"


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_create_returns_the_new_patient(api: TestClient) -> None:
    response = _post(api, {"full_name": "  Sample Ada  ", "phone": " +91 98765 43210 "})
    assert response.status_code == 201
    body = response.json()
    assert body["patient_number"] == 1
    assert body["display_id"] == "P-0001"
    assert body["full_name"] == "Sample Ada"
    assert body["phone"] == "+91 98765 43210"
    assert body["date_of_birth"] is None
    assert body["id"]
    assert body["created_at"]


def test_blank_name_is_rejected_and_saves_nothing(api: TestClient) -> None:
    _assert_rejected(api, {"full_name": "   ", "phone": _PHONE}, "full_name", "   ")


def test_a_long_name_is_rejected_and_saves_nothing(api: TestClient) -> None:
    name = "A" * 201
    _assert_rejected(api, {"full_name": name, "phone": _PHONE}, "full_name", name)


def test_a_blank_phone_is_rejected_and_saves_nothing(api: TestClient) -> None:
    _assert_rejected(api, {"full_name": "Sample Ada", "phone": "   "}, "phone", "   ")


def test_a_short_phone_is_rejected_and_saves_nothing(api: TestClient) -> None:
    _assert_rejected(api, {"full_name": "Sample Ada", "phone": "123-456"}, "phone", "123-456")


def test_a_long_phone_is_rejected_and_saves_nothing(api: TestClient) -> None:
    phone = "1" * 16
    _assert_rejected(api, {"full_name": "Sample Ada", "phone": phone}, "phone", phone)


def test_a_phone_with_letters_is_rejected_and_saves_nothing(api: TestClient) -> None:
    _assert_rejected(
        api, {"full_name": "Sample Ada", "phone": "call-9000000001"}, "phone", "call-9000000001"
    )


def test_a_future_date_of_birth_is_rejected_and_saves_nothing(api: TestClient) -> None:
    future = "2999-01-01"
    _assert_rejected(
        api,
        {"full_name": "Sample Ada", "phone": _PHONE, "date_of_birth": future},
        "date_of_birth",
        future,
    )


def test_a_date_of_birth_before_1900_is_rejected_and_saves_nothing(api: TestClient) -> None:
    early = "1899-12-31"
    _assert_rejected(
        api,
        {"full_name": "Sample Ada", "phone": _PHONE, "date_of_birth": early},
        "date_of_birth",
        early,
    )


def test_the_date_edges_are_accepted(api: TestClient) -> None:
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    first = _post(api, {"full_name": "Sample Ada", "phone": _PHONE, "date_of_birth": "1900-01-01"})
    second = _post(
        api,
        {"full_name": "Sample Bea", "phone": "9000000002", "date_of_birth": today.isoformat()},
    )
    assert first.status_code == 201
    assert first.json()["date_of_birth"] == "1900-01-01"
    assert second.status_code == 201
    assert second.json()["date_of_birth"] == today.isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    rejected = _post(
        api,
        {"full_name": "Sample Cee", "phone": "9000000003", "date_of_birth": tomorrow},
    )
    assert rejected.status_code == 422
    assert tomorrow not in rejected.json()["error"]["message"]


def test_duplicate_names_and_phones_are_allowed(api: TestClient) -> None:
    body = {"full_name": "Sample Ada", "phone": _PHONE}
    first = _post(api, body)
    second = _post(api, body)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["display_id"] == "P-0001"
    assert second.json()["display_id"] == "P-0002"
    listed = api.get("/patients", cookies=_cookie(api))
    assert listed.status_code == 200
    assert listed.json()["total"] == 2


@pytest.mark.parametrize("email", ["receptionist@x.test", "clinician@x.test", "admin@x.test"])
def test_the_three_roles_can_create_and_list(api: TestClient, email: str) -> None:
    cookie = {"dc_session": login(api, email)}
    created = api.post(
        "/patients",
        cookies=cookie,
        json={"full_name": "Sample Ada", "phone": _PHONE},
    )
    assert created.status_code == 201
    listed = api.get("/patients", cookies=cookie)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


def test_inventory_admin_cannot_create_or_list(api: TestClient) -> None:
    _post(api, {"full_name": "Sample Ada", "phone": _PHONE})
    cookie = {"dc_session": login(api, "inventory@x.test")}
    created = api.post(
        "/patients",
        cookies=cookie,
        json={"full_name": "Sample Bea", "phone": "9000000002"},
    )
    listed = api.get("/patients", cookies=cookie)
    assert created.status_code == 403
    assert listed.status_code == 403
    assert created.json()["error"]["code"] == "forbidden"
    assert "Sample" not in created.json()["error"]["message"]
    assert api.get("/patients", cookies=_cookie(api)).json()["total"] == 1


def test_no_session_is_rejected(api: TestClient) -> None:
    created = api.post("/patients", json={"full_name": "Sample Ada", "phone": _PHONE})
    listed = api.get("/patients")
    assert created.status_code == 401
    assert listed.status_code == 401
    assert created.json()["error"]["code"] == "unauthenticated"
    assert _stored_counts() == (0, 0)


def test_another_clinic_cannot_see_the_patient(api: TestClient) -> None:
    created = _post(api, {"full_name": "Sample Ada", "phone": _PHONE})
    display_id = created.json()["display_id"]
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        actor = create_user(
            session,
            other.id,
            "other@x.test",
            "Synthetic Person",
            "synthetic-password-marker",
            ["receptionist"],
        )
        own = register_patient(session, other.id, actor.id, "Sample Bea", "9000000002", None)
        session.commit()
        own_display_id = own.display_id
    cookie = {"dc_session": login(api, "other@x.test")}
    listed = api.get("/patients", cookies=cookie)
    assert listed.status_code == 200
    assert [item["display_id"] for item in listed.json()["items"]] == [own_display_id]
    found = api.get("/patients", cookies=cookie, params={"q": display_id})
    assert [item["full_name"] for item in found.json()["items"]] == ["Sample Bea"]
    assert found.json()["items"][0]["id"] != created.json()["id"]


def test_patient_routes_list_their_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    roles = _roles(create_app())
    assert roles[("POST", "/patients")] == set(PATIENT_ROLES)
    assert roles[("GET", "/patients")] == set(PATIENT_ROLES)
    assert "inventory_admin" not in roles[("GET", "/patients")]


def _post(api: TestClient, body: Mapping[str, Any]) -> Response:
    return cast(Response, api.post("/patients", cookies=_cookie(api), json=body))


def _cookie(api: TestClient) -> dict[str, str]:
    return {"dc_session": login(api, "receptionist@x.test")}


def _assert_rejected(api: TestClient, body: Mapping[str, Any], field: str, marker: str) -> None:
    response = api.post("/patients", cookies=_cookie(api), json=body)
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert response.json()["error"]["code"] == "validation_error"
    assert f"body.{field}" in message
    assert marker not in response.text
    assert _stored_counts() == (0, 0)


def _stored_counts() -> tuple[int, int]:
    with Session(get_engine()) as session:
        patients = session.scalar(select(func.count()).select_from(Patient))
        events = session.scalar(select(func.count()).select_from(AuditEvent))
    return int(patients or 0), int(events or 0)


def _roles(application: FastAPI) -> dict[tuple[str, str], set[str]]:
    found: dict[tuple[str, str], set[str]] = {}
    for route in iter_api_routes(application):
        if not isinstance(route, APIRoute):
            continue
        allowed: set[str] = set()
        for dep in route.dependant.dependencies:
            listed = getattr(dep.call, "allowed_roles", None)
            if listed:
                allowed.update(listed)
        for method in route.methods or ():
            if method == "HEAD":
                continue
            found[(method, route.path)] = allowed
    return found
