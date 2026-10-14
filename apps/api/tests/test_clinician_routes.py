"""GET /clinicians: active clinicians in the caller's clinic, and nobody else."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.appointment import APPOINTMENT_ROLES
from dentacircle.main import create_app
from dentacircle.models.app_user import AppUser
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import PASSWORD, login, patient_api
from tests.test_access import iter_api_routes


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_the_list_is_active_clinicians_sorted_by_name(api: TestClient) -> None:
    with Session(get_engine()) as session:
        clinic_id = session.scalars(select(AppUser.clinic_id).limit(1)).one()
        create_user(
            session,
            clinic_id,
            "zed@x.test",
            "Zed Person",
            PASSWORD,
            ["clinician"],
        )
        idle = create_user(session, clinic_id, "idle@x.test", "Ada Idle", PASSWORD, ["clinician"])
        idle.is_active = False
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        create_user(
            session,
            other.id,
            "other-clinician@x.test",
            "Aaron Other",
            PASSWORD,
            ["clinician"],
        )
        session.commit()
    response = api.get("/clinicians", cookies=_cookie(api, "receptionist@x.test"))
    assert response.status_code == 200
    body = response.json()
    assert [row["full_name"] for row in body] == ["Synthetic Person", "Zed Person"]
    assert set(body[0]) == {"id", "full_name"}


@pytest.mark.parametrize("email", ["receptionist@x.test", "clinician@x.test", "admin@x.test"])
def test_the_three_roles_can_list_clinicians(api: TestClient, email: str) -> None:
    response = api.get("/clinicians", cookies=_cookie(api, email))
    assert response.status_code == 200


def test_inventory_admin_and_a_missing_session_are_rejected(api: TestClient) -> None:
    forbidden = api.get("/clinicians", cookies=_cookie(api, "inventory@x.test"))
    api.cookies.clear()
    missing = api.get("/clinicians")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden"
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "unauthenticated"


def test_the_route_lists_its_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    roles = _roles(create_app())
    assert roles[("GET", "/clinicians")] == set(APPOINTMENT_ROLES)
    assert "inventory_admin" not in roles[("GET", "/clinicians")]


def _cookie(api: TestClient, email: str) -> dict[str, str]:
    return {"dc_session": login(api, email)}


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
