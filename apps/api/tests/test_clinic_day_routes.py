"""GET and PUT /clinic/day."""

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


def _interval(weekday: int, opens_at: str, closes_at: str) -> dict[str, object]:
    return {"weekday": weekday, "opens_at": opens_at, "closes_at": closes_at}


def _body(
    working_hours: list[dict[str, object]],
    timezone: str = "Asia/Kolkata",
    minutes: int = 30,
) -> dict[str, object]:
    return {
        "timezone": timezone,
        "default_appointment_minutes": minutes,
        "working_hours": working_hours,
    }


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


def test_any_signed_in_role_can_read_the_default_day(api: TestClient) -> None:
    for email in _USERS:
        response = api.get("/clinic/day", cookies={"dc_session": _login(api, email)})
        assert response.status_code == 200
        body = response.json()
        assert body["timezone"] == "Asia/Kolkata"
        assert body["default_appointment_minutes"] == 30
        assert body["working_hours"] == [
            {"weekday": weekday, "opens_at": "09:00:00", "closes_at": "18:00:00"}
            for weekday in range(6)
        ]


def test_no_session_is_rejected(api: TestClient) -> None:
    response = api.get("/clinic/day")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize("email", ["clinician@x.test", "receptionist@x.test", "inventory@x.test"])
def test_only_clinic_admin_can_change_the_day(api: TestClient, email: str) -> None:
    response = api.put(
        "/clinic/day",
        cookies={"dc_session": _login(api, email)},
        json=_body([]),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_admin_replaces_hours_and_an_empty_list_closes_every_day(api: TestClient) -> None:
    cookie = {"dc_session": _login(api, "admin@x.test")}
    hours = (
        [_interval(weekday, "09:00:00", "13:00:00") for weekday in range(5)]
        + [_interval(weekday, "14:00:00", "18:00:00") for weekday in range(5)]
        + [_interval(6, "10:00:00", "12:00:00")]
    )
    hours.reverse()
    closed_saturday = _body(hours, timezone="Asia/Dubai", minutes=20)
    # Sunday was placed first in the request. The response is ordered by weekday, then start.
    updated = api.put("/clinic/day", cookies=cookie, json=closed_saturday)
    assert updated.status_code == 200
    body = updated.json()
    assert body["timezone"] == "Asia/Dubai"
    assert body["default_appointment_minutes"] == 20
    assert [row["weekday"] for row in body["working_hours"]] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 6]
    assert body["working_hours"][0] == {
        "weekday": 0,
        "opens_at": "09:00:00",
        "closes_at": "13:00:00",
    }
    assert all(row["weekday"] != 5 for row in body["working_hours"])

    emptied = api.put("/clinic/day", cookies=cookie, json=_body([]))
    assert emptied.status_code == 200
    assert emptied.json()["working_hours"] == []
    assert api.get("/clinic/day", cookies=cookie).json()["working_hours"] == []


@pytest.mark.parametrize(
    ("payload", "marker", "location"),
    [
        (_body([], timezone="Not/AZone"), "Not/AZone", "timezone"),
        (_body([_interval(0, "15:00:00", "09:00:00")]), "15:00:00", "working_hours"),
        (_body([_interval(9, "09:00:00", "10:00:00")]), "9", "weekday"),
        (
            _body(
                [
                    _interval(0, "09:00:00", "12:00:00"),
                    _interval(0, "11:30:00", "13:00:00"),
                ]
            ),
            "11:30:00",
            "body",
        ),
        (
            _body(
                [
                    _interval(0, "09:00:00", "12:00:00"),
                    _interval(0, "12:00:00", "15:00:00"),
                ]
            ),
            "12:00:00",
            "body",
        ),
        (
            _body([_interval(1, f"{hour:02d}:10:00", f"{hour:02d}:20:00") for hour in range(7)]),
            "06:10:00",
            "body",
        ),
        (_body([], minutes=4), "4", "default_appointment_minutes"),
        (_body([], minutes=481), "481", "default_appointment_minutes"),
    ],
)
def test_invalid_day_is_a_422_and_changes_nothing(
    api: TestClient, payload: dict[str, object], marker: str, location: str
) -> None:
    cookie = {"dc_session": _login(api, "admin@x.test")}
    before = api.get("/clinic/day", cookies=cookie).json()
    response = api.put("/clinic/day", cookies=cookie, json=payload)
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert response.json()["error"]["code"] == "validation_error"
    assert location in message
    assert marker not in message
    assert api.get("/clinic/day", cookies=cookie).json() == before


def test_day_routes_list_their_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    roles = _roles(create_app())
    assert roles[("GET", "/clinic/day")] == set(ROLES)
    assert roles[("PUT", "/clinic/day")] == {"clinic_admin"}


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
