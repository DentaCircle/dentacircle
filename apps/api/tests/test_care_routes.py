"""Care routes: bodies, check order, roles, and tenancy."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.care import CARE_READ_ROLES, CARE_WRITE_ROLES
from dentacircle.main import create_app
from dentacircle.models.app_user import AppUser
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_plan import CarePlan
from dentacircle.services.care_service import add_item, create_plan
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes

_MARKER = "care-marker-value"
_ROLES = ("receptionist", "clinician", "clinic_admin", "inventory_admin")
_EMAILS = {
    "receptionist": "receptionist@x.test",
    "clinician": "clinician@x.test",
    "clinic_admin": "admin@x.test",
    "inventory_admin": "inventory@x.test",
}
_WRITE_ROUTES = (
    ("POST", "/patients/{patient_id}/care-plans"),
    ("PATCH", "/care-plans/{plan_id}"),
    ("POST", "/care-plans/{plan_id}/items"),
    ("PATCH", "/care-items/{item_id}"),
    ("POST", "/care-items/{item_id}/status"),
)


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_create_returns_a_closed_plan(api: TestClient) -> None:
    patient_id = _patient(api)
    created = api.post(
        f"/patients/{patient_id}/care-plans",
        cookies=_cookie(api, "clinician@x.test"),
        json={"title": "  Sample plan  "},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["patient_id"] == patient_id
    assert body["title"] == "Sample plan"
    assert body["is_open"] is False
    assert body["items"] == []
    assert set(body) == {"id", "patient_id", "title", "created_at", "is_open", "items"}


def test_an_item_starts_planned(api: TestClient) -> None:
    plan_id = _plan(api)
    created = api.post(
        f"/care-plans/{plan_id}/items",
        cookies=_cookie(api, "clinician@x.test"),
        json={"name": "  Sample service  "},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Sample service"
    assert body["status"] == "planned"
    assert set(body) == {"id", "name", "status", "created_at"}


def test_a_bad_body_is_422_and_does_not_echo_the_value(api: TestClient) -> None:
    patient_id = _patient(api)
    plan_id = _plan(api, patient_id)
    item_id = _item(api, plan_id)
    _finish(item_id)
    cases = [
        ("POST", f"/patients/{patient_id}/care-plans", {"title": ""}),
        ("POST", f"/patients/{patient_id}/care-plans", {"title": "x" * 201}),
        ("POST", f"/patients/{patient_id}/care-plans", {"title": "Ok", "note": _MARKER}),
        ("POST", f"/care-plans/{plan_id}/items", {"name": "   "}),
        ("PATCH", f"/care-plans/{plan_id}", {"title": "Ok", "status": _MARKER}),
        ("PATCH", f"/care-items/{item_id}", {"name": "Ok", "status": "started"}),
        ("POST", f"/care-items/{item_id}/status", {"status": "planned"}),
        ("POST", f"/care-items/{item_id}/status", {"status": _MARKER}),
        ("POST", f"/care-items/{item_id}/status", {}),
    ]
    for method, path, payload in cases:
        before = _counts()
        response = api.request(method, path, cookies=_cookie(api, "clinician@x.test"), json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert _MARKER not in response.text
        assert "started" not in response.text or method != "PATCH"
        assert _counts() == before


def test_checks_run_in_order(api: TestClient) -> None:
    missing = str(uuid4())
    leaked = {"status": _MARKER}
    anonymous = api.post(f"/care-items/{missing}/status", json=leaked)
    assert anonymous.status_code == 401
    assert _MARKER not in anonymous.text

    inventory = api.post(
        f"/care-items/{missing}/status",
        cookies=_cookie(api, "inventory@x.test"),
        json=leaked,
    )
    assert inventory.status_code == 403
    assert _MARKER not in inventory.text

    unknown = api.post(
        f"/care-items/{missing}/status",
        cookies=_cookie(api, "clinician@x.test"),
        json=leaked,
    )
    assert unknown.status_code == 404
    assert _MARKER not in unknown.text

    item_id = _item(api, _plan(api))
    _finish(item_id)
    bad_and_illegal = api.post(
        f"/care-items/{item_id}/status",
        cookies=_cookie(api, "clinician@x.test"),
        json={"status": "planned"},
    )
    assert bad_and_illegal.status_code == 422
    illegal = api.post(
        f"/care-items/{item_id}/status",
        cookies=_cookie(api, "clinician@x.test"),
        json={"status": "started"},
    )
    assert illegal.status_code == 409
    assert illegal.json()["error"]["code"] == "invalid_status"


def test_every_role_on_every_write_route(api: TestClient) -> None:
    patient_id = _patient(api)
    plan_id = _plan(api, patient_id)
    item_id = _item(api, plan_id)
    for role in _ROLES:
        for method, path in _WRITE_ROUTES:
            _reset(plan_id, item_id)
            before = _rows()
            response = api.request(
                method,
                _fill(path, patient_id, plan_id, item_id),
                cookies=_cookie(api, _EMAILS[role]),
                json=_body(method, path),
            )
            if role in CARE_WRITE_ROLES:
                assert response.status_code in (200, 201)
            else:
                assert response.status_code == 403
                assert _rows() == before


def test_reading_is_open_to_the_desk_and_closed_to_inventory(api: TestClient) -> None:
    patient_id = _patient(api)
    plan_id = _plan(api, patient_id)
    _item(api, plan_id)
    for role in ("receptionist", "clinician", "clinic_admin"):
        found = api.get(
            f"/patients/{patient_id}/care-plans",
            cookies=_cookie(api, _EMAILS[role]),
        )
        assert found.status_code == 200
        assert len(found.json()) == 1
    denied = api.get(
        f"/patients/{patient_id}/care-plans",
        cookies=_cookie(api, "inventory@x.test"),
    )
    assert denied.status_code == 403
    api.cookies.clear()
    anonymous = api.get(f"/patients/{patient_id}/care-plans")
    assert anonymous.status_code == 401


def test_another_clinic_is_not_found_and_not_listed(api: TestClient) -> None:
    own_patient = _patient(api)
    other_patient, other_plan, other_item = _other_clinic_care()
    cookies = _cookie(api, "clinician@x.test")
    listed = api.get(f"/patients/{own_patient}/care-plans", cookies=cookies)
    assert listed.status_code == 200
    assert listed.json() == []
    for method, path in (
        ("GET", f"/patients/{other_patient}/care-plans"),
        ("POST", f"/patients/{other_patient}/care-plans"),
        ("PATCH", f"/care-plans/{other_plan}"),
        ("POST", f"/care-plans/{other_plan}/items"),
        ("PATCH", f"/care-items/{other_item}"),
        ("POST", f"/care-items/{other_item}/status"),
    ):
        response = api.request(method, path, cookies=cookies, json=_body(method, path))
        assert response.status_code == 404


def test_an_inactive_patient_blocks_new_care_only(api: TestClient) -> None:
    patient_id = _patient(api)
    plan_id = _plan(api, patient_id)
    item_id = _item(api, plan_id)
    with Session(get_engine()) as session:
        actor = session.scalars(select(CarePlan).where(CarePlan.id == UUID(plan_id))).one()
        set_patient_status(session, actor.clinic_id, _actor_id(api), UUID(patient_id), "inactive")
        session.commit()
    cookies = _cookie(api, "clinician@x.test")
    created = api.post(
        f"/patients/{patient_id}/care-plans",
        cookies=cookies,
        json={"title": "Another"},
    )
    added = api.post(f"/care-plans/{plan_id}/items", cookies=cookies, json={"name": "Another"})
    assert created.status_code == 409
    assert created.json()["error"]["code"] == "patient_inactive"
    assert added.status_code == 409
    assert added.json()["error"]["code"] == "patient_inactive"
    renamed = api.patch(f"/care-items/{item_id}", cookies=cookies, json={"name": "Wrap up"})
    moved = api.post(f"/care-items/{item_id}/status", cookies=cookies, json={"status": "completed"})
    assert renamed.status_code == 200
    assert moved.status_code == 200
    listed = api.get(f"/patients/{patient_id}/care-plans", cookies=cookies)
    assert listed.status_code == 200
    assert listed.json()[0]["items"][0]["status"] == "completed"


def test_care_routes_declare_their_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    found = _route_roles(create_app())
    read = set(CARE_READ_ROLES)
    write = set(CARE_WRITE_ROLES)
    assert found[("GET", "/patients/{patient_id}/care-plans")] == read
    for method, path in _WRITE_ROUTES:
        assert found[(method, path)] == write


def _patient(api: TestClient) -> str:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": "Sample Ada", "phone": "9000000001"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _plan(api: TestClient, patient_id: str | None = None) -> str:
    if patient_id is None:
        patient_id = _patient(api)
    response = api.post(
        f"/patients/{patient_id}/care-plans",
        cookies=_cookie(api, "clinician@x.test"),
        json={"title": "Sample plan"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _item(api: TestClient, plan_id: str) -> str:
    response = api.post(
        f"/care-plans/{plan_id}/items",
        cookies=_cookie(api, "clinician@x.test"),
        json={"name": "Sample service"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _finish(item_id: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(CareItem, UUID(item_id))
        assert row is not None
        row.status = "completed"
        session.commit()


def _reset(plan_id: str, item_id: str) -> None:
    with Session(get_engine()) as session:
        plan = session.get(CarePlan, UUID(plan_id))
        item = session.get(CareItem, UUID(item_id))
        assert plan is not None and item is not None
        plan.title = "Sample plan"
        item.name = "Sample service"
        item.status = "planned"
        session.commit()


def _fill(path: str, patient_id: str, plan_id: str, item_id: str) -> str:
    return (
        path.replace("{patient_id}", patient_id)
        .replace("{plan_id}", plan_id)
        .replace("{item_id}", item_id)
    )


def _body(method: str, path: str) -> dict[str, str]:
    if path.endswith("/status"):
        return {"status": "started"}
    if method == "POST" and path.endswith("/items"):
        return {"name": "Added"}
    if "care-items" in path:
        return {"name": "Renamed service"}
    return {"title": "Renamed plan"}


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _counts() -> tuple[int, int, int]:
    with Session(get_engine()) as session:
        plans = session.scalar(select(func.count()).select_from(CarePlan))
        items = session.scalar(select(func.count()).select_from(CareItem))
        audits = session.scalar(select(func.count()).select_from(AuditEvent))
    return int(plans or 0), int(items or 0), int(audits or 0)


def _rows() -> tuple[list[tuple[str, str]], list[tuple[str, str, str]], int]:
    with Session(get_engine()) as session:
        plans = [
            (str(row.id), row.title)
            for row in session.scalars(select(CarePlan).order_by(CarePlan.id))
        ]
        items = [
            (str(row.id), row.name, row.status)
            for row in session.scalars(select(CareItem).order_by(CareItem.id))
        ]
        audits = session.scalar(select(func.count()).select_from(AuditEvent))
    return plans, items, int(audits or 0)


def _actor_id(api: TestClient) -> UUID:
    del api
    with Session(get_engine()) as session:
        user = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        return user.id


def _other_clinic_care() -> tuple[str, str, str]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Other Clinic")
        actor = create_user(
            session,
            clinic.id,
            "other@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, "Sample Bea", "9000000002", None)
        plan = create_plan(session, clinic.id, actor.id, patient.id, "Other plan")
        item = add_item(session, clinic.id, actor.id, plan.id, "Other service")
        session.commit()
        return str(patient.id), str(plan.id), str(item.id)


def _route_roles(application: FastAPI) -> dict[tuple[str, str], set[str]]:
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
