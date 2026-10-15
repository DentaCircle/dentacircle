"""POST /appointments/{id}/status: body, check order, roles, and tenancy."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, tzinfo
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.appointment import APPOINTMENT_ROLES
from dentacircle.main import create_app
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes

_ZONE = ZoneInfo("Asia/Kolkata")
_FIXED = datetime(2026, 10, 15, 10, 0, tzinfo=_ZONE)
_MARKER = "status-marker-value"
_ROLES = ("receptionist", "clinician", "clinic_admin", "inventory_admin")
_TARGETS = ("arrived", "in_progress", "completed", "no_show")
_FROM = {
    "arrived": "scheduled",
    "no_show": "scheduled",
    "in_progress": "arrived",
    "completed": "in_progress",
}
_ALLOWED = {
    ("receptionist", "arrived"),
    ("receptionist", "no_show"),
    ("clinician", "arrived"),
    ("clinician", "in_progress"),
    ("clinician", "completed"),
    ("clinician", "no_show"),
    ("clinic_admin", "arrived"),
    ("clinic_admin", "in_progress"),
    ("clinic_admin", "completed"),
    ("clinic_admin", "no_show"),
}


class _FrozenDateTime:
    @staticmethod
    def now(tz: tzinfo | None = None) -> datetime:
        if tz is None:
            return _FIXED.astimezone(UTC).replace(tzinfo=None)
        return _FIXED.astimezone(tz)


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dentacircle.api.appointments.datetime", _FrozenDateTime)


def test_a_successful_change_matches_the_calendar_item(api: TestClient, clock: None) -> None:
    visit_id = _visit(api, _FIXED, "scheduled")
    changed = api.post(
        f"/appointments/{visit_id}/status",
        cookies=_cookie(api, "clinician@x.test"),
        json={"status": "arrived"},
    )
    assert changed.status_code == 200
    body = changed.json()
    assert body["id"] == visit_id
    assert body["status"] == "arrived"
    assert set(body) == {
        "id",
        "starts_at",
        "ends_at",
        "status",
        "patient",
        "clinician",
        "appointment_type",
    }
    assert body["patient"]["full_name"] == "Sample Ada"


@pytest.mark.parametrize(
    ("payload", "names_status"),
    [
        ({}, True),
        ({"status": "scheduled"}, True),
        ({"status": "cancelled"}, True),
        ({"status": _MARKER}, True),
        ({"status": "arrived", "note": _MARKER}, False),
    ],
)
def test_a_bad_body_is_422_and_does_not_echo_the_value(
    api: TestClient, clock: None, payload: dict[str, str], names_status: bool
) -> None:
    visit_id = _visit(api, _FIXED, "scheduled")
    before = _counts()
    response = api.post(
        f"/appointments/{visit_id}/status",
        cookies=_cookie(api),
        json=payload,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    if names_status:
        assert "status" in response.json()["error"]["message"]
    assert _MARKER not in response.text
    assert _counts() == before


def test_checks_run_in_order(api: TestClient, clock: None) -> None:
    missing = str(uuid4())
    leaked = {"status": _MARKER}
    anonymous = api.post(f"/appointments/{missing}/status", json=leaked)
    assert anonymous.status_code == 401
    assert _MARKER not in anonymous.text

    inventory = api.post(
        f"/appointments/{missing}/status",
        cookies=_cookie(api, "inventory@x.test"),
        json=leaked,
    )
    assert inventory.status_code == 403
    assert _MARKER not in inventory.text

    unknown = api.post(
        f"/appointments/{missing}/status",
        cookies=_cookie(api),
        json=leaked,
    )
    assert unknown.status_code == 404
    assert _MARKER not in unknown.text

    visit_id = _visit(api, _FIXED + timedelta(days=1), "scheduled")
    skipped = api.post(
        f"/appointments/{visit_id}/status",
        cookies=_cookie(api, "clinician@x.test"),
        json={"status": "completed"},
    )
    assert skipped.status_code == 409
    assert skipped.json()["error"]["code"] == "invalid_status"
    assert "not_today" not in skipped.text

    arrived = api.post(
        f"/appointments/{visit_id}/status",
        cookies=_cookie(api),
        json={"status": "arrived"},
    )
    assert arrived.status_code == 422
    assert "not_today" in arrived.json()["error"]["message"]
    assert "body.status" in arrived.json()["error"]["message"]

    later = _visit(api, _FIXED + timedelta(hours=1), "scheduled")
    early = api.post(
        f"/appointments/{later}/status",
        cookies=_cookie(api),
        json={"status": "no_show"},
    )
    assert early.status_code == 422
    assert "not_started" in early.json()["error"]["message"]


def test_every_role_and_target(api: TestClient, clock: None) -> None:
    emails = {
        "receptionist": "receptionist@x.test",
        "clinician": "clinician@x.test",
        "clinic_admin": "admin@x.test",
        "inventory_admin": "inventory@x.test",
    }
    visit_id = _visit(api, _FIXED, "scheduled")
    for role in _ROLES:
        for target in _TARGETS:
            _set_status(UUID(visit_id), _FROM[target])
            before = _counts()
            response = api.post(
                f"/appointments/{visit_id}/status",
                cookies=_cookie(api, emails[role]),
                json={"status": target},
            )
            if (role, target) in _ALLOWED:
                assert response.status_code == 200
                assert response.json()["status"] == target
            else:
                assert response.status_code == 403
                assert _counts() == before
                with Session(get_engine()) as session:
                    row = session.get(Appointment, UUID(visit_id))
                    assert row is not None
                    assert row.status == _FROM[target]


def test_no_session_is_401(api: TestClient, clock: None) -> None:
    visit_id = _visit(api, _FIXED, "scheduled")
    api.cookies.clear()
    response = api.post(f"/appointments/{visit_id}/status", json={"status": "arrived"})
    assert response.status_code == 401
    with Session(get_engine()) as session:
        row = session.get(Appointment, UUID(visit_id))
        assert row is not None
        assert row.status == "scheduled"


def test_another_clinic_cannot_change_status(api: TestClient, clock: None) -> None:
    visit_id = _visit(api, _FIXED, "scheduled")
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        create_user(
            session,
            other.id,
            "other@x.test",
            "Other Desk",
            "synthetic-password-marker",
            ["receptionist"],
        )
        session.commit()
    response = api.post(
        f"/appointments/{visit_id}/status",
        cookies={"dc_session": login(api, "other@x.test")},
        json={"status": "arrived"},
    )
    assert response.status_code == 404
    assert visit_id not in response.text
    with Session(get_engine()) as session:
        row = session.get(Appointment, UUID(visit_id))
        assert row is not None
        assert row.status == "scheduled"


def test_the_route_names_the_booking_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    roles = _route_roles(create_app())
    assert roles[("POST", "/appointments/{appointment_id}/status")] == set(APPOINTMENT_ROLES)


def _visit(api: TestClient, start: datetime, status: str) -> str:
    patient_id, clinician_id, type_id, clinic_id = _ids(api)
    visit_id = uuid4()
    with Session(get_engine()) as session:
        AppointmentRepository(session, UUID(clinic_id)).add(
            Appointment(
                id=visit_id,
                patient_id=UUID(patient_id),
                clinician_user_id=UUID(clinician_id),
                appointment_type_id=UUID(type_id),
                starts_at=start,
                ends_at=start + timedelta(minutes=30),
                status=status,
            )
        )
        session.commit()
    return str(visit_id)


def _ids(api: TestClient) -> tuple[str, str, str, str]:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": "Sample Ada", "phone": "9000000001"},
    )
    assert response.status_code == 201
    patient_id = str(response.json()["id"])
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
        return patient_id, str(clinician.id), str(consultation.id), str(clinician.clinic_id)


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _set_status(appointment_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        row.status = status
        session.commit()


def _counts() -> tuple[int, int]:
    with Session(get_engine()) as session:
        rows = session.scalar(select(func.count()).select_from(Appointment))
        audits = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "appointment")
        )
    return int(rows or 0), int(audits or 0)


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
