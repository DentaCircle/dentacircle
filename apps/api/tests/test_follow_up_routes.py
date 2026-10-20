"""GET /patients/{id}/follow-up: one open row, check order, roles, and tenancy."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.appointment import APPOINTMENT_ROLES
from dentacircle.domain.follow_up import (
    FOLLOW_UP_CREATE_ROLES,
    FOLLOW_UP_QUEUE_ROLES,
    FOLLOW_UP_READ_ROLES,
)
from dentacircle.main import create_app
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.follow_up import FollowUp
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.services.care_service import add_item, create_plan
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes, unmarked_routes

_ZONE = ZoneInfo("Asia/Kolkata")
_START = datetime(2026, 10, 17, 10, 0, tzinfo=_ZONE)
_ROLES = ("receptionist", "clinician", "clinic_admin", "inventory_admin")
_EMAILS = {
    "receptionist": "receptionist@x.test",
    "clinician": "clinician@x.test",
    "clinic_admin": "admin@x.test",
    "inventory_admin": "inventory@x.test",
}
_MARKER = "follow-up-marker-value"
_FIELDS = {"id", "patient_id", "appointment_id", "status", "due_on", "created_at"}
_VISIT_FIELDS = {
    "id",
    "starts_at",
    "ends_at",
    "status",
    "patient",
    "clinician",
    "appointment_type",
}


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_get_returns_the_open_follow_up_or_null(api: TestClient) -> None:
    patient_id = _patient(api)
    cookies = _cookie(api, "clinician@x.test")
    empty = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
    assert empty.status_code == 200
    assert empty.json() == {"follow_up": None}

    visit_id = _in_progress(api, patient_id)
    _item(api, patient_id)
    completed = api.post(
        f"/appointments/{visit_id}/status",
        cookies=cookies,
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    assert set(completed.json()) == _VISIT_FIELDS
    assert completed.json()["status"] == "completed"

    found = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
    assert found.status_code == 200
    body = found.json()
    assert set(body) == {"follow_up"}
    row = body["follow_up"]
    assert set(row) == _FIELDS
    assert row["patient_id"] == patient_id
    assert row["appointment_id"] == visit_id
    assert row["status"] == "scheduled"
    due_on = row["due_on"]
    assert isinstance(due_on, str)
    assert "T" not in due_on
    assert due_on == _expected_due()
    assert _MARKER not in found.text

    _set_status(UUID(row["id"]), "completed")
    closed = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
    assert closed.status_code == 200
    assert closed.json() == {"follow_up": None}
    _set_status(UUID(row["id"]), "cancelled")
    cancelled = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
    assert cancelled.json() == {"follow_up": None}


def test_checks_run_session_then_role_then_patient(api: TestClient) -> None:
    missing = str(uuid4())
    api.cookies.clear()
    anonymous = api.get(f"/patients/{missing}/follow-up")
    assert anonymous.status_code == 401
    denied = api.get(f"/patients/{missing}/follow-up", cookies=_cookie(api, "inventory@x.test"))
    assert denied.status_code == 403
    unknown = api.get(f"/patients/{missing}/follow-up", cookies=_cookie(api, "clinician@x.test"))
    assert unknown.status_code == 404
    assert _MARKER not in unknown.text


def test_every_role_on_the_read_leaves_the_table_unchanged(api: TestClient) -> None:
    patient_id = _patient(api)
    visit_id = _in_progress(api, patient_id)
    _item(api, patient_id)
    completed = api.post(
        f"/appointments/{visit_id}/status",
        cookies=_cookie(api, "clinician@x.test"),
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    before = _snapshot()
    for role in _ROLES:
        response = api.get(
            f"/patients/{patient_id}/follow-up",
            cookies=_cookie(api, _EMAILS[role]),
        )
        if role in FOLLOW_UP_READ_ROLES:
            assert response.status_code == 200
            assert response.json()["follow_up"]["status"] == "scheduled"
        else:
            assert response.status_code == 403
        assert _snapshot() == before
    api.cookies.clear()
    anonymous = api.get(f"/patients/{patient_id}/follow-up")
    assert anonymous.status_code == 401
    assert _snapshot() == before


def test_get_returns_a_null_appointment_for_a_manual_follow_up(api: TestClient) -> None:
    patient_id = _patient(api)
    cookies = _cookie(api, "clinician@x.test")
    due_on = datetime.now(UTC).astimezone(_ZONE).date() + timedelta(days=2)
    created = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=cookies,
        json={"due_on": due_on.isoformat()},
    )
    assert created.status_code == 201
    found = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
    assert found.status_code == 200
    row = found.json()["follow_up"]
    assert row["appointment_id"] is None
    assert row["due_on"] == due_on.isoformat()
    assert row["status"] == "scheduled"
    assert set(row) == _FIELDS


def test_another_clinic_is_not_found(api: TestClient) -> None:
    own = _patient(api)
    other = _other_patient()
    cookies = _cookie(api, "clinician@x.test")
    response = api.get(f"/patients/{other}/follow-up", cookies=cookies)
    assert response.status_code == 404
    assert _MARKER not in response.text
    own_response = api.get(f"/patients/{own}/follow-up", cookies=cookies)
    assert own_response.status_code == 200
    assert own_response.json() == {"follow_up": None}


def test_follow_up_routes_declare_their_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    application = create_app()
    assert unmarked_routes(application) == []
    found = _route_roles(application)
    assert found[("GET", "/patients/{patient_id}/follow-up")] == set(FOLLOW_UP_READ_ROLES)
    assert found[("POST", "/patients/{patient_id}/follow-up")] == set(FOLLOW_UP_CREATE_ROLES)
    assert found[("GET", "/follow-ups")] == set(FOLLOW_UP_QUEUE_ROLES)
    assert found[("POST", "/follow-ups/{follow_up_id}/contacted")] == set(FOLLOW_UP_QUEUE_ROLES)
    assert found[("POST", "/follow-ups/{follow_up_id}/book")] == set(FOLLOW_UP_QUEUE_ROLES)
    assert found[("POST", "/appointments/{appointment_id}/status")] == set(APPOINTMENT_ROLES)


def test_refused_roles_leave_the_tables_unchanged_on_all_three_queue_routes(
    api: TestClient,
) -> None:
    follow_up_id, clinician_id, type_id = _queue_ids(api)
    start = datetime.now(_ZONE).date() + timedelta(days=2)
    while start.weekday() == 6:
        start += timedelta(days=1)
    starts_at = datetime(start.year, start.month, start.day, 10, 0, tzinfo=_ZONE)
    body = {
        "clinician_id": clinician_id,
        "appointment_type_id": type_id,
        "starts_at": starts_at.isoformat(),
    }
    before = _snapshot()
    for email, expected in (("inventory@x.test", 403),):
        cookies = _cookie(api, email)
        listed = api.get("/follow-ups", cookies=cookies)
        contacted = api.post(f"/follow-ups/{follow_up_id}/contacted", cookies=cookies)
        booked = api.post(f"/follow-ups/{follow_up_id}/book", cookies=cookies, json=body)
        assert listed.status_code == expected
        assert contacted.status_code == expected
        assert booked.status_code == expected
        assert _snapshot() == before
    api.cookies.clear()
    listed = api.get("/follow-ups")
    contacted = api.post(f"/follow-ups/{follow_up_id}/contacted")
    booked = api.post(f"/follow-ups/{follow_up_id}/book", json=body)
    assert listed.status_code == 401
    assert contacted.status_code == 401
    assert booked.status_code == 401
    assert _snapshot() == before
    for email in ("receptionist@x.test", "clinician@x.test", "admin@x.test"):
        listed = api.get("/follow-ups", cookies=_cookie(api, email))
        assert listed.status_code == 200
        assert listed.json()["items"][0]["id"] == follow_up_id


def _queue_ids(api: TestClient) -> tuple[str, str, str]:
    patient_id = _patient(api)
    due_on = datetime.now(UTC).astimezone(_ZONE).date()
    created = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": due_on.isoformat()},
    )
    assert created.status_code == 201
    with Session(get_engine()) as session:
        clinician = session.scalars(
            select(AppUser).where(AppUser.email == "clinician@x.test")
        ).one()
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinician.clinic_id)
            )
            if row.name == "Consultation"
        )
        return str(created.json()["follow_up"]["id"]), str(clinician.id), str(consultation.id)


def _expected_due() -> str:
    local_today = datetime.now(UTC).astimezone(_ZONE).date()
    return (local_today + timedelta(days=7)).isoformat()


def _patient(api: TestClient) -> str:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": "Sample Ada", "phone": "9000000001"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _item(api: TestClient, patient_id: str) -> None:
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        plan = create_plan(session, actor.clinic_id, actor.id, UUID(patient_id), "Sample plan")
        add_item(session, actor.clinic_id, actor.id, plan.id, "Sample service")
        session.commit()


def _in_progress(api: TestClient, patient_id: str) -> str:
    with Session(get_engine()) as session:
        clinician = session.scalars(
            select(AppUser).where(AppUser.email == "clinician@x.test")
        ).one()
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinician.clinic_id)
            )
            if row.name == "Consultation"
        )
        visit_id = uuid4()
        AppointmentRepository(session, clinician.clinic_id).add(
            Appointment(
                id=visit_id,
                patient_id=UUID(patient_id),
                clinician_user_id=clinician.id,
                appointment_type_id=consultation.id,
                starts_at=_START,
                ends_at=_START + timedelta(minutes=30),
                status="in_progress",
            )
        )
        session.commit()
        return str(visit_id)


def _other_patient() -> str:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Other Clinic")
        actor = create_user(
            session,
            clinic.id,
            "b@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, _MARKER, "9000000002", None)
        session.commit()
        return str(patient.id)


def _set_status(follow_up_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE follow_up SET status = :status WHERE id = :id"),
            {"status": status, "id": follow_up_id},
        )
        session.commit()


def _snapshot() -> tuple[list[tuple[str, str, str, str]], int]:
    with Session(get_engine()) as session:
        rows = [
            (str(row.id), str(row.appointment_id), row.status, row.due_on.isoformat())
            for row in session.scalars(select(FollowUp).order_by(FollowUp.id))
        ]
        audits = session.scalar(select(func.count()).select_from(AuditEvent))
    return rows, int(audits or 0)


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
