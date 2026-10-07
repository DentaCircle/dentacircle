"""Appointment type routes."""

from collections.abc import Iterator

import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.roles import ROLES
from dentacircle.main import create_app
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_access import iter_api_routes
from tests.test_migrations import _config

_PASSWORD = "synthetic-password-marker"
_USERS = {
    "clinician@x.test": ["clinician"],
    "receptionist@x.test": ["receptionist"],
    "inventory@x.test": ["inventory_admin"],
    "admin@x.test": ["clinic_admin"],
}
_SEEDED = ["Consultation", "Crown visit", "Root canal visit", "Scaling"]


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    command.upgrade(_config(), "head")
    clear_engine()
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        for email, roles in _USERS.items():
            create_user(session, clinic.id, email, "Synthetic Person", _PASSWORD, roles)
        session.commit()
    with TestClient(create_app()) as client:
        yield client


def test_any_signed_in_role_lists_active_types_by_name(api: TestClient) -> None:
    for email in _USERS:
        response = api.get("/appointment-types", cookies={"dc_session": _login(api, email)})
        assert response.status_code == 200
        rows = response.json()
        assert [row["name"] for row in rows] == _SEEDED
        consultation = rows[0]
        assert consultation["duration_minutes"] == 30
        assert consultation["effective_duration_minutes"] == 30
        assert consultation["is_active"] is True


def test_no_session_is_rejected(api: TestClient) -> None:
    response = api.get("/appointment-types")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize("email", ["clinician@x.test", "receptionist@x.test", "inventory@x.test"])
def test_only_clinic_admin_can_change_types(api: TestClient, email: str) -> None:
    cookie = {"dc_session": _login(api, email)}
    created = api.post(
        "/appointment-types", cookies=cookie, json={"name": "Polish", "duration_minutes": 20}
    )
    assert created.status_code == 403
    listed = api.get("/appointment-types", cookies={"dc_session": _login(api, "admin@x.test")})
    type_id = listed.json()[0]["id"]
    updated = api.put(
        f"/appointment-types/{type_id}",
        cookies=cookie,
        json={"name": "Consultation", "duration_minutes": 30, "is_active": False},
    )
    assert updated.status_code == 403


def test_admin_creates_trims_and_rejects_a_duplicate_or_a_bad_type(api: TestClient) -> None:
    cookie = {"dc_session": _login(api, "admin@x.test")}
    created = api.post(
        "/appointment-types",
        cookies=cookie,
        json={"name": "  Polish  ", "duration_minutes": None},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Polish"
    assert body["duration_minutes"] is None
    assert body["effective_duration_minutes"] == 30
    assert body["is_active"] is True

    duplicate = api.post(
        "/appointment-types", cookies=cookie, json={"name": "polish", "duration_minutes": 20}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"
    assert duplicate.json()["error"]["message"] == "That name is already in use."
    assert "polish" not in duplicate.json()["error"]["message"]

    blank = api.post(
        "/appointment-types", cookies=cookie, json={"name": "   ", "duration_minutes": 20}
    )
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "validation_error"
    assert "   " not in blank.json()["error"]["message"]

    for minutes in (4, 481):
        bad = api.post(
            "/appointment-types",
            cookies=cookie,
            json={"name": "Review", "duration_minutes": minutes},
        )
        assert bad.status_code == 422
        assert str(minutes) not in bad.json()["error"]["message"]

    omitted = api.post("/appointment-types", cookies=cookie, json={"name": "Review"})
    assert omitted.status_code == 201
    assert omitted.json()["duration_minutes"] is None
    assert omitted.json()["effective_duration_minutes"] == 30

    names = [row["name"] for row in api.get("/appointment-types", cookies=cookie).json()]
    assert names == [
        "Consultation",
        "Crown visit",
        "Polish",
        "Review",
        "Root canal visit",
        "Scaling",
    ]


def test_update_replaces_the_type_and_deactivate_hides_it(api: TestClient) -> None:
    cookie = {"dc_session": _login(api, "admin@x.test")}
    created = api.post(
        "/appointment-types", cookies=cookie, json={"name": "Polish", "duration_minutes": 20}
    )
    type_id = created.json()["id"]
    renamed = api.put(
        f"/appointment-types/{type_id}",
        cookies=cookie,
        json={"name": " polish ", "duration_minutes": None, "is_active": True},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "polish"
    assert renamed.json()["duration_minutes"] is None
    assert renamed.json()["effective_duration_minutes"] == 30

    hidden = api.put(
        f"/appointment-types/{type_id}",
        cookies=cookie,
        json={"name": "polish", "duration_minutes": 20, "is_active": False},
    )
    assert hidden.status_code == 200
    active = [row["name"] for row in api.get("/appointment-types", cookies=cookie).json()]
    assert "polish" not in active
    included = api.get("/appointment-types", cookies=cookie, params={"include_inactive": True})
    assert any(row["name"] == "polish" and row["is_active"] is False for row in included.json())


def test_update_unknown_id_is_404_and_another_types_name_is_409(api: TestClient) -> None:
    cookie = {"dc_session": _login(api, "admin@x.test")}
    missing = api.put(
        "/appointment-types/33333333-3333-3333-3333-333333333333",
        cookies=cookie,
        json={"name": "Polish", "duration_minutes": 20, "is_active": True},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert "33333333" not in missing.json()["error"]["message"]

    listed = api.get("/appointment-types", cookies=cookie).json()
    consultation = next(row for row in listed if row["name"] == "Consultation")
    clash = api.put(
        f"/appointment-types/{consultation['id']}",
        cookies=cookie,
        json={"name": "scaling", "duration_minutes": 30, "is_active": True},
    )
    assert clash.status_code == 409
    assert "scaling" not in clash.json()["error"]["message"]
    names = [row["name"] for row in api.get("/appointment-types", cookies=cookie).json()]
    assert "Consultation" in names
    assert names.count("Scaling") == 1


def test_type_routes_list_their_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    roles = _roles(create_app())
    assert roles[("GET", "/appointment-types")] == set(ROLES)
    assert roles[("POST", "/appointment-types")] == {"clinic_admin"}
    assert roles[("PUT", "/appointment-types/{type_id}")] == {"clinic_admin"}


def _login(client: TestClient, email: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": _PASSWORD})
    assert response.status_code == 200
    return str(response.cookies["dc_session"])


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
