"""GET /patients/{id}/timeline: shape, check order, roles, and no write route."""

from collections.abc import Iterator
from typing import get_args
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.api.timeline import TimelineKind
from dentacircle.core.database import get_engine
from dentacircle.domain.timeline import TIMELINE_KINDS, TIMELINE_READ_ROLES
from dentacircle.main import create_app
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.timeline_event import TimelineEvent
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes, unmarked_routes

_ROLES = ("receptionist", "clinician", "clinic_admin", "inventory_admin")
_EMAILS = {
    "receptionist": "receptionist@x.test",
    "clinician": "clinician@x.test",
    "clinic_admin": "admin@x.test",
    "inventory_admin": "inventory@x.test",
}


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_response_kinds_match_domain() -> None:
    assert set(get_args(TimelineKind)) == set(TIMELINE_KINDS)


def test_get_returns_the_page_newest_first(api: TestClient) -> None:
    patient_id = _patient(api)
    cookies = _cookie(api, "clinician@x.test")
    found = api.get(f"/patients/{patient_id}/timeline", cookies=cookies)
    assert found.status_code == 200
    body = found.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    item = body["items"][0]
    assert set(item) == {"id", "kind", "occurred_at", "actor", "subject"}
    assert item["kind"] == "patient_registered"
    assert item["subject"] is None
    assert set(item["actor"]) == {"id", "name"}
    assert item["actor"]["name"] == "Synthetic Person"
    assert "Sample" not in found.text


def test_checks_run_session_then_role_then_validation_then_patient(api: TestClient) -> None:
    missing = str(uuid4())
    api.cookies.clear()
    anonymous = api.get(f"/patients/{missing}/timeline", params={"page": 0})
    assert anonymous.status_code == 401
    denied = api.get(
        f"/patients/{missing}/timeline",
        cookies=_cookie(api, "inventory@x.test"),
        params={"page": 0},
    )
    assert denied.status_code == 403
    cookies = _cookie(api, "clinician@x.test")
    for params in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        response = api.get(f"/patients/{missing}/timeline", cookies=cookies, params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
    unknown = api.get(f"/patients/{missing}/timeline", cookies=cookies)
    assert unknown.status_code == 404
    bad_id = api.get("/patients/not-a-uuid/timeline", cookies=cookies)
    assert bad_id.status_code == 422


def test_every_role_and_an_inactive_patient(api: TestClient) -> None:
    patient_id = _patient(api)
    _set_inactive(patient_id)
    before = _audit_count()
    for role in _ROLES:
        response = api.get(
            f"/patients/{patient_id}/timeline",
            cookies=_cookie(api, _EMAILS[role]),
        )
        if role in TIMELINE_READ_ROLES:
            assert response.status_code == 200
            assert response.json()["items"][0]["kind"] == "patient_registered"
        else:
            assert response.status_code == 403
            assert patient_id not in response.text
    api.cookies.clear()
    assert api.get(f"/patients/{patient_id}/timeline").status_code == 401
    assert _audit_count() == before
    assert _event_count() == 1


def test_there_is_no_route_that_writes_a_timeline_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    application = create_app()
    assert unmarked_routes(application) == []
    found = _route_roles(application)
    assert found[("GET", "/patients/{patient_id}/timeline")] == set(TIMELINE_READ_ROLES)
    writers = [(method, path) for method, path in found if "timeline" in path and method != "GET"]
    assert writers == []


def _patient(api: TestClient) -> str:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": "Sample Ada", "phone": "9000000001"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _set_inactive(patient_id: str) -> None:
    with Session(get_engine()) as session:
        from dentacircle.models.patient import Patient

        row = session.get(Patient, UUID(patient_id))
        assert row is not None
        row.status = "inactive"
        session.commit()


def _audit_count() -> int:
    with Session(get_engine()) as session:
        count = session.scalar(select(func.count()).select_from(AuditEvent))
    return int(count or 0)


def _event_count() -> int:
    with Session(get_engine()) as session:
        count = session.scalar(select(func.count()).select_from(TimelineEvent))
    return int(count or 0)


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


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
