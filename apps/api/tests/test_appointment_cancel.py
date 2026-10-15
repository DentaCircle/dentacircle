"""Cancel a scheduled visit, free the slot, and leave every other status alone."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.appointment import APPOINTMENT_ROLES
from dentacircle.main import create_app
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.appointment_service import (
    AppointmentNotFoundError,
    InvalidStatusError,
    book_appointment,
    cancel_appointment,
    find_availability,
    get_appointment,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 14, 8, 0, tzinfo=_ZONE)
_START = datetime(2026, 10, 15, 10, 0, tzinfo=_ZONE)
_NAME = "Sample Ada"


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_cancel_sets_status_and_writes_one_audit_without_values(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    with Session(get_engine()) as session:
        cancelled = cancel_appointment(session, clinic_id, actor_id, appointment_id, _NOW)
        session.commit()
    assert cancelled.status == "cancelled"
    assert cancelled.patient.full_name == _NAME
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("appointment", appointment_id)
        assert [event.action for event in events] == ["create", "status_change"]
        change = events[1]
        assert change.entity_type == "appointment"
        assert change.changed_fields == ["status"]
        assert change.actor_user_id == actor_id
        row = (
            session.execute(text("SELECT * FROM audit_event WHERE action = 'status_change'"))
            .mappings()
            .one()
        )
        stored = " ".join(str(value) for value in row.values())
    assert _NAME not in stored
    assert "scheduled" not in stored
    assert "cancelled" not in stored


def test_a_cancelled_slot_can_be_booked_again(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    with Session(get_engine()) as session:
        second = register_patient(session, clinic_id, actor_id, "Sample Bea", "9000000002", None)
        cancel_appointment(session, clinic_id, actor_id, appointment_id, _NOW)
        session.commit()
        second_id = second.id
    with Session(get_engine()) as session:
        slots = find_availability(session, clinic_id, clinician_id, type_id, _START.date(), _NOW)
        assert any(slot.starts_at == _START for slot in slots.slots)
        book_appointment(
            session, clinic_id, actor_id, second_id, clinician_id, type_id, _START, _NOW
        )
        session.commit()
    with Session(get_engine()) as session:
        blocking = session.scalar(
            select(func.count()).select_from(Appointment).where(Appointment.status == "scheduled")
        )
    assert blocking == 1


@pytest.mark.parametrize("status", ["arrived", "in_progress", "completed", "cancelled", "no_show"])
def test_any_status_but_scheduled_is_rejected(database: str, status: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    _set_status(appointment_id, status)
    with Session(get_engine()) as session:
        before = _appointment_audits(session)
        with pytest.raises(InvalidStatusError):
            cancel_appointment(session, clinic_id, actor_id, appointment_id, _NOW)
        session.commit()
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.status == status
        assert _appointment_audits(session) == before


def test_an_unknown_or_other_clinic_visit_is_missing(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        session.commit()
        other_id = other.id
    with Session(get_engine()) as session:
        with pytest.raises(AppointmentNotFoundError):
            get_appointment(session, clinic_id, uuid4(), _NOW)
        with pytest.raises(AppointmentNotFoundError):
            get_appointment(session, other_id, appointment_id, _NOW)
        with pytest.raises(AppointmentNotFoundError):
            cancel_appointment(session, other_id, actor_id, appointment_id, _NOW)
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.status == "scheduled"


def test_a_failed_audit_write_does_not_save_the_cancel(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            cancel_appointment(session, clinic_id, uuid4(), appointment_id, _NOW)
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.status == "scheduled"
        assert _appointment_audits(session) == 1


def test_get_and_cancel_over_http(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    start = _future_at(10, 0)
    booked = api.post(
        "/appointments",
        cookies=_cookie(api),
        json={
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": start.isoformat(),
        },
    )
    assert booked.status_code == 201
    appointment_id = str(booked.json()["id"])
    found = api.get(f"/appointments/{appointment_id}", cookies=_cookie(api))
    assert found.status_code == 200
    assert found.json()["patient"]["full_name"] == "Sample Ada"
    assert found.json()["status"] == "scheduled"
    cancelled = api.post(f"/appointments/{appointment_id}/cancel", cookies=_cookie(api))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["id"] == appointment_id
    listed = api.get("/appointments", cookies=_cookie(api), params=_span(start))
    assert listed.json() == []
    free = api.get(
        "/appointments/availability",
        cookies=_cookie(api),
        params={
            "date": start.date().isoformat(),
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
        },
    )
    assert any(slot["starts_at"] == start.isoformat() for slot in free.json()["slots"])
    second = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": "Sample Bea", "phone": "9000000002"},
    )
    assert second.status_code == 201
    again = api.post(
        "/appointments",
        cookies=_cookie(api),
        json={
            "patient_id": second.json()["id"],
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": start.isoformat(),
        },
    )
    assert again.status_code == 201


def test_a_missing_visit_is_404_and_the_id_is_not_echoed(api: TestClient) -> None:
    missing = str(uuid4())
    found = api.get(f"/appointments/{missing}", cookies=_cookie(api))
    cancelled = api.post(f"/appointments/{missing}/cancel", cookies=_cookie(api))
    assert found.status_code == 404
    assert cancelled.status_code == 404
    assert missing not in found.text
    assert missing not in cancelled.text


def test_a_visit_that_is_not_scheduled_cannot_be_cancelled(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    start = _future_at(11, 0)
    booked = api.post(
        "/appointments",
        cookies=_cookie(api),
        json={
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": start.isoformat(),
        },
    )
    appointment_id = str(booked.json()["id"])
    _set_status(UUID(appointment_id), "arrived")
    before = _counts()
    rejected = api.post(f"/appointments/{appointment_id}/cancel", cookies=_cookie(api))
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "invalid_status"
    assert appointment_id not in rejected.text
    assert _counts() == before
    with Session(get_engine()) as session:
        row = session.get(Appointment, UUID(appointment_id))
        assert row is not None
        assert row.status == "arrived"


@pytest.mark.parametrize("email", ["receptionist@x.test", "clinician@x.test", "admin@x.test"])
def test_the_three_roles_can_read_and_cancel(api: TestClient, email: str) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    hour = {"receptionist@x.test": 10, "clinician@x.test": 11, "admin@x.test": 12}[email]
    booked = api.post(
        "/appointments",
        cookies=_cookie(api),
        json={
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": _future_at(hour, 0).isoformat(),
        },
    )
    appointment_id = str(booked.json()["id"])
    found = api.get(f"/appointments/{appointment_id}", cookies=_cookie(api, email))
    cancelled = api.post(f"/appointments/{appointment_id}/cancel", cookies=_cookie(api, email))
    assert found.status_code == 200
    assert cancelled.status_code == 200


def test_inventory_admin_and_a_missing_session_are_rejected(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    booked = api.post(
        "/appointments",
        cookies=_cookie(api),
        json={
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": _future_at(10, 0).isoformat(),
        },
    )
    appointment_id = str(booked.json()["id"])
    inventory = {"dc_session": login(api, "inventory@x.test")}
    for cookies, expected in ((inventory, 403), (None, 401)):
        if cookies is None:
            api.cookies.clear()
        found = api.get(f"/appointments/{appointment_id}", cookies=cookies)
        cancelled = api.post(f"/appointments/{appointment_id}/cancel", cookies=cookies)
        assert found.status_code == expected
        assert cancelled.status_code == expected
    with Session(get_engine()) as session:
        row = session.get(Appointment, UUID(appointment_id))
        assert row is not None
        assert row.status == "scheduled"


def test_another_clinic_cannot_read_or_cancel(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    booked = api.post(
        "/appointments",
        cookies=_cookie(api),
        json={
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": _future_at(10, 0).isoformat(),
        },
    )
    appointment_id = str(booked.json()["id"])
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
    cookie = {"dc_session": login(api, "other@x.test")}
    found = api.get(f"/appointments/{appointment_id}", cookies=cookie)
    cancelled = api.post(f"/appointments/{appointment_id}/cancel", cookies=cookie)
    assert found.status_code == 404
    assert cancelled.status_code == 404
    assert appointment_id not in found.text
    assert patient_id not in cancelled.text


def test_the_routes_name_their_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    roles = _roles(create_app())
    assert roles[("GET", "/appointments/{appointment_id}")] == set(APPOINTMENT_ROLES)
    assert roles[("POST", "/appointments/{appointment_id}/cancel")] == set(APPOINTMENT_ROLES)


def _world() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "desk@x.test",
            "Sample Desk",
            "synthetic-password-marker",
            ["receptionist"],
        )
        clinician = create_user(
            session,
            clinic.id,
            "clinician@x.test",
            "Sample Clinician",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, _NAME, "9000000001", None)
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        return clinic.id, actor.id, clinician.id, patient.id, consultation.id


def _book(
    clinic_id: UUID,
    actor_id: UUID,
    patient_id: UUID,
    clinician_id: UUID,
    type_id: UUID,
    start: datetime,
) -> UUID:
    with Session(get_engine()) as session:
        created = book_appointment(
            session, clinic_id, actor_id, patient_id, clinician_id, type_id, start, _NOW
        )
        session.commit()
        return created.id


def _set_status(appointment_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        row.status = status
        session.commit()


def _appointment_audits(session: Session) -> int:
    count = session.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "appointment")
    )
    return int(count or 0)


def _ids(api: TestClient) -> tuple[str, str, str]:
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
        return patient_id, str(clinician.id), str(consultation.id)


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _future_at(hour: int, minute: int) -> datetime:
    now = datetime.now(_ZONE)
    day = now.date() + timedelta(days=1)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=_ZONE)


def _span(start: datetime) -> dict[str, str]:
    day = start.date().isoformat()
    return {"from": day, "to": day}


def _counts() -> tuple[int, int]:
    with Session(get_engine()) as session:
        rows = session.scalar(select(func.count()).select_from(Appointment))
        audits = _appointment_audits(session)
    return int(rows or 0), audits


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
