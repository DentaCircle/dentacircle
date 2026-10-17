"""Care session routes: bodies, check order, roles, and tenancy."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.care_session import CARE_SESSION_READ_ROLES, CARE_SESSION_WRITE_ROLES
from dentacircle.main import create_app
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_session import CareSession
from dentacircle.services.appointment_service import book_appointment, change_status
from dentacircle.services.care_service import change_item_status
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes

_ZONE = ZoneInfo("Asia/Kolkata")
_DAY = datetime(2026, 10, 17, 9, 0, tzinfo=_ZONE)
_ROLES = ("receptionist", "clinician", "clinic_admin", "inventory_admin")
_EMAILS = {
    "receptionist": "receptionist@x.test",
    "clinician": "clinician@x.test",
    "clinic_admin": "admin@x.test",
    "inventory_admin": "inventory@x.test",
}
_MARKER = "session-marker-value"
_SLOT = {"n": 0}


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    _SLOT["n"] = 0
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_get_is_null_until_a_session_is_saved(api: TestClient) -> None:
    visit_id, item_id, _patient_id = _arrived(api)
    cookies = _cookie(api, "clinician@x.test")
    empty = api.get(f"/appointments/{visit_id}/care-session", cookies=cookies)
    assert empty.status_code == 200
    assert empty.json() == {"session": None}
    saved = api.post(
        f"/appointments/{visit_id}/care-session",
        cookies=cookies,
        json={"items": [{"care_item_id": item_id, "status": "completed"}]},
    )
    assert saved.status_code == 201
    body = saved.json()
    assert set(body) == {
        "id",
        "appointment_id",
        "patient_id",
        "recorded_by_name",
        "created_at",
        "items",
    }
    assert body["appointment_id"] == visit_id
    assert body["recorded_by_name"] == "Synthetic Person"
    assert body["items"] == [
        {
            "care_item_id": item_id,
            "name": "Sample service",
            "plan_title": "Sample plan",
            "status": "completed",
        }
    ]
    filled = api.get(f"/appointments/{visit_id}/care-session", cookies=cookies)
    assert filled.status_code == 200
    assert filled.json()["session"]["id"] == body["id"]
    visit = api.get(f"/appointments/{visit_id}", cookies=cookies)
    assert visit.status_code == 200
    assert visit.json()["status"] == "arrived"


def test_a_bad_body_is_422_and_does_not_echo_the_value(api: TestClient) -> None:
    visit_id, item_id, _patient_id = _arrived(api)
    cookies = _cookie(api, "clinician@x.test")
    cases = [
        {"items": []},
        {"items": [{"care_item_id": item_id, "status": "started"}] * 21},
        {"items": [{"care_item_id": item_id, "status": "cancelled"}]},
        {"items": [{"care_item_id": item_id, "status": "started"}], "note": _MARKER},
        {"items": [{"care_item_id": item_id, "status": "started", "tooth": _MARKER}]},
        {
            "items": [
                {"care_item_id": item_id, "status": "started"},
                {"care_item_id": item_id, "status": "completed"},
            ]
        },
    ]
    for payload in cases:
        before = _snapshot()
        response = api.post(f"/appointments/{visit_id}/care-session", cookies=cookies, json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert _MARKER not in response.text
        assert _snapshot() == before


def test_checks_run_in_order(api: TestClient) -> None:
    missing = str(uuid4())
    leaked = {"items": [{"care_item_id": missing, "status": "started"}], "note": _MARKER}
    anonymous = api.post(f"/appointments/{missing}/care-session", json=leaked)
    assert anonymous.status_code == 401
    assert _MARKER not in anonymous.text

    inventory = api.post(
        f"/appointments/{missing}/care-session",
        cookies=_cookie(api, "inventory@x.test"),
        json=leaked,
    )
    assert inventory.status_code == 403
    assert _MARKER not in inventory.text

    unknown = api.post(
        f"/appointments/{missing}/care-session",
        cookies=_cookie(api, "clinician@x.test"),
        json=leaked,
    )
    assert unknown.status_code == 404
    assert _MARKER not in unknown.text

    scheduled, _item_id, _patient_id = _visit(api, "scheduled")
    bad_first = api.post(
        f"/appointments/{scheduled}/care-session",
        cookies=_cookie(api, "clinician@x.test"),
        json={"items": [], "note": _MARKER},
    )
    assert bad_first.status_code == 422
    assert _MARKER not in bad_first.text

    refused = api.post(
        f"/appointments/{scheduled}/care-session",
        cookies=_cookie(api, "clinician@x.test"),
        json={"items": [{"care_item_id": _item_id, "status": "started"}]},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "invalid_status"

    visit_id, item_id, _patient_id = _arrived(api)
    cookies = _cookie(api, "clinician@x.test")
    first = api.post(
        f"/appointments/{visit_id}/care-session",
        cookies=cookies,
        json={"items": [{"care_item_id": item_id, "status": "started"}]},
    )
    assert first.status_code == 201
    second = api.post(
        f"/appointments/{visit_id}/care-session",
        cookies=cookies,
        json={"items": [{"care_item_id": str(uuid4()), "status": "completed"}]},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "session_exists"

    fresh, _own, _patient = _arrived(api)
    unknown_item = api.post(
        f"/appointments/{fresh}/care-session",
        cookies=cookies,
        json={"items": [{"care_item_id": str(uuid4()), "status": "started"}]},
    )
    assert unknown_item.status_code == 422
    assert "unknown_item" in unknown_item.json()["error"]["message"]
    assert unknown_item.json()["error"]["code"] == "validation_error"

    changed_visit, changed_item, _patient = _arrived(api)
    _complete(changed_item)
    changed = api.post(
        f"/appointments/{changed_visit}/care-session",
        cookies=cookies,
        json={"items": [{"care_item_id": changed_item, "status": "completed"}]},
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "item_changed"


def test_every_role_on_both_routes(api: TestClient) -> None:
    for role in _ROLES:
        visit_id, item_id, _patient_id = _arrived(api)
        before = _snapshot()
        posted = api.post(
            f"/appointments/{visit_id}/care-session",
            cookies=_cookie(api, _EMAILS[role]),
            json={"items": [{"care_item_id": item_id, "status": "started"}]},
        )
        if role in CARE_SESSION_WRITE_ROLES:
            assert posted.status_code == 201
        else:
            assert posted.status_code == 403
            assert _snapshot() == before
        fetched = api.get(
            f"/appointments/{visit_id}/care-session",
            cookies=_cookie(api, _EMAILS[role]),
        )
        if role in CARE_SESSION_READ_ROLES:
            assert fetched.status_code == 200
        else:
            assert fetched.status_code == 403
            assert _snapshot() == before


def test_another_clinic_visit_is_not_found(api: TestClient) -> None:
    visit_id = _other_clinic_visit()
    cookies = _cookie(api, "clinician@x.test")
    fetched = api.get(f"/appointments/{visit_id}/care-session", cookies=cookies)
    posted = api.post(
        f"/appointments/{visit_id}/care-session",
        cookies=cookies,
        json={"items": [{"care_item_id": str(uuid4()), "status": "started"}]},
    )
    assert fetched.status_code == 404
    assert posted.status_code == 404


def test_an_inactive_patient_can_still_be_recorded(api: TestClient) -> None:
    visit_id, item_id, patient_id = _arrived(api)
    with Session(get_engine()) as session:
        set_patient_status(session, _clinic_id(), _actor_id(), UUID(patient_id), "inactive")
        session.commit()
    saved = api.post(
        f"/appointments/{visit_id}/care-session",
        cookies=_cookie(api, "clinician@x.test"),
        json={"items": [{"care_item_id": item_id, "status": "completed"}]},
    )
    assert saved.status_code == 201


def test_care_session_routes_declare_their_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    found = _route_roles(create_app())
    assert found[("GET", "/appointments/{appointment_id}/care-session")] == set(
        CARE_SESSION_READ_ROLES
    )
    assert found[("POST", "/appointments/{appointment_id}/care-session")] == set(
        CARE_SESSION_WRITE_ROLES
    )


def _arrived(api: TestClient) -> tuple[str, str, str]:
    return _visit(api, "arrived")


def _visit(api: TestClient, status: str) -> tuple[str, str, str]:
    patient = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": "Sample Ada", "phone": "9000000001"},
    )
    assert patient.status_code == 201
    patient_id = str(patient.json()["id"])
    plan = api.post(
        f"/patients/{patient_id}/care-plans",
        cookies=_cookie(api, "clinician@x.test"),
        json={"title": "Sample plan"},
    )
    assert plan.status_code == 201
    item = api.post(
        f"/care-plans/{plan.json()['id']}/items",
        cookies=_cookie(api, "clinician@x.test"),
        json={"name": "Sample service"},
    )
    assert item.status_code == 201
    item_id = str(item.json()["id"])
    start = _DAY + timedelta(minutes=30 * _SLOT["n"])
    _SLOT["n"] += 1
    clinic_id, actor_id, type_id = _booking_ids()
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            UUID(patient_id),
            actor_id,
            type_id,
            start,
            start - timedelta(hours=1),
        )
        session.commit()
        visit_id = created.id
    if status == "arrived":
        with Session(get_engine()) as session:
            change_status(session, clinic_id, actor_id, ["clinician"], visit_id, "arrived", start)
            session.commit()
    return str(visit_id), item_id, patient_id


def _complete(item_id: str) -> None:
    with Session(get_engine()) as session:
        change_item_status(session, _clinic_id(), _actor_id(), UUID(item_id), "completed")
        session.commit()


def _booking_ids() -> tuple[UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        user = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == user.clinic_id)
            )
            if row.name == "Consultation"
        )
        return user.clinic_id, user.id, consultation.id


def _clinic_id() -> UUID:
    return _booking_ids()[0]


def _actor_id() -> UUID:
    return _booking_ids()[1]


def _other_clinic_visit() -> str:
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
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        clinic_id, actor_id, patient_id, type_id = clinic.id, actor.id, patient.id, consultation.id
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            actor_id,
            type_id,
            _DAY,
            _DAY - timedelta(hours=1),
        )
        change_status(session, clinic_id, actor_id, ["clinician"], created.id, "arrived", _DAY)
        session.commit()
        return str(created.id)


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _snapshot() -> tuple[int, list[tuple[str, str]], int]:
    with Session(get_engine()) as session:
        sessions = session.scalar(select(func.count()).select_from(CareSession))
        items = [
            (str(row.id), row.status)
            for row in session.scalars(select(CareItem).order_by(CareItem.id))
        ]
        audits = session.scalar(select(func.count()).select_from(AuditEvent))
    return int(sessions or 0), items, int(audits or 0)


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
