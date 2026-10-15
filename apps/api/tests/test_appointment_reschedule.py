"""Move a scheduled visit: same length, optional clinician, one audit row."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.appointment import APPOINTMENT_ROLES, AppointmentFieldError
from dentacircle.main import create_app
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.appointment_service import (
    AppointmentNotFoundError,
    InvalidStatusError,
    PatientBusyError,
    SlotTakenError,
    book_appointment,
    reschedule_appointment,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 14, 8, 0, tzinfo=_ZONE)
_START = datetime(2026, 10, 15, 9, 0, tzinfo=_ZONE)


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


def test_a_move_into_the_old_span_keeps_the_length(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    later = _START.replace(minute=15)
    with Session(get_engine()) as session:
        moved = reschedule_appointment(
            session, clinic_id, actor_id, appointment_id, later, None, _NOW
        )
        session.commit()
    assert moved.starts_at == later
    assert moved.ends_at == later + timedelta(minutes=30)
    assert moved.clinician.id == clinician_id
    assert moved.patient.id == patient_id
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("appointment", appointment_id)
        change = events[1]
    assert change.action == "update"
    assert change.changed_fields == ["starts_at", "ends_at"]


def test_the_same_start_and_clinician_is_unchanged(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    with Session(get_engine()) as session:
        before = _audits(session)
        with pytest.raises(AppointmentFieldError) as caught:
            reschedule_appointment(
                session, clinic_id, actor_id, appointment_id, _START, clinician_id, _NOW
            )
    assert caught.value.field == "starts_at"
    assert caught.value.code == "unchanged"
    with Session(get_engine()) as session:
        assert _audits(session) == before


def test_omitting_the_clinician_keeps_an_inactive_one(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    with Session(get_engine()) as session:
        stored = session.get(AppUser, clinician_id)
        assert stored is not None
        stored.is_active = False
        session.commit()
    later = _START.replace(hour=11)
    with Session(get_engine()) as session:
        moved = reschedule_appointment(
            session, clinic_id, actor_id, appointment_id, later, None, _NOW
        )
        session.commit()
    assert moved.clinician.id == clinician_id
    assert moved.starts_at == later
    with Session(get_engine()) as session:
        with pytest.raises(AppointmentFieldError) as caught:
            reschedule_appointment(
                session,
                clinic_id,
                actor_id,
                appointment_id,
                _START.replace(hour=12),
                clinician_id,
                _NOW,
            )
    assert caught.value.field == "clinician_id"
    assert caught.value.code == "inactive"


def test_changing_clinician_is_recorded(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    other = _clinician(clinic_id, "two@x.test", "Second Clinician")
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    with Session(get_engine()) as session:
        moved = reschedule_appointment(
            session, clinic_id, actor_id, appointment_id, _START.replace(hour=11), other, _NOW
        )
        session.commit()
    assert moved.clinician.id == other
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("appointment", appointment_id)
        change = events[1]
    assert change.changed_fields == ["starts_at", "ends_at", "clinician_user_id"]


def test_a_taken_clinician_or_a_busy_patient_is_rejected(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    other = _clinician(clinic_id, "two@x.test", "Second Clinician")
    with Session(get_engine()) as session:
        second = register_patient(session, clinic_id, actor_id, "Sample Bea", "9000000002", None)
        session.commit()
        second_id = second.id
    _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    taken = _book(clinic_id, actor_id, second_id, other, type_id, _START.replace(hour=11))
    moving = _book(clinic_id, actor_id, patient_id, other, type_id, _START.replace(hour=12))
    with Session(get_engine()) as session:
        with pytest.raises(SlotTakenError):
            reschedule_appointment(session, clinic_id, actor_id, taken, _START, clinician_id, _NOW)
    with Session(get_engine()) as session:
        with pytest.raises(PatientBusyError):
            reschedule_appointment(session, clinic_id, actor_id, moving, _START, None, _NOW)
        row = session.get(Appointment, moving)
        assert row is not None
        assert row.starts_at == _START.replace(hour=12)


def test_bad_starts_and_a_bad_clinician_name_the_field(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    cases = [
        (datetime(2026, 10, 15, 10, 0), None, "timezone_naive"),
        (_START.replace(year=2020), None, "past"),
        (_START.replace(year=2028), None, "beyond_horizon"),
        (_START.replace(hour=8), None, "outside_hours"),
        (_START.replace(minute=7), None, "not_on_grid"),
    ]
    for start, clinician, code in cases:
        with Session(get_engine()) as session:
            with pytest.raises(AppointmentFieldError) as caught:
                reschedule_appointment(
                    session, clinic_id, actor_id, appointment_id, start, clinician, _NOW
                )
        assert caught.value.field == "starts_at"
        assert caught.value.code == code
    with Session(get_engine()) as session:
        with pytest.raises(AppointmentFieldError) as caught:
            reschedule_appointment(
                session, clinic_id, actor_id, appointment_id, _START.replace(hour=11), uuid4(), _NOW
            )
    assert caught.value.field == "clinician_id"


def test_a_visit_that_is_not_scheduled_cannot_move(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        row.status = "arrived"
        session.commit()
        before = _audits(session)
        with pytest.raises(InvalidStatusError):
            reschedule_appointment(
                session, clinic_id, actor_id, appointment_id, _START.replace(hour=11), None, _NOW
            )
    with Session(get_engine()) as session:
        assert _audits(session) == before
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.starts_at == _START


def test_another_clinic_and_a_failed_audit_save_nothing(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id, _START)
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        session.commit()
        other_id = other.id
    with Session(get_engine()) as session:
        with pytest.raises(AppointmentNotFoundError):
            reschedule_appointment(
                session, other_id, actor_id, appointment_id, _START.replace(hour=11), None, _NOW
            )
        with pytest.raises(IntegrityError):
            reschedule_appointment(
                session, clinic_id, uuid4(), appointment_id, _START.replace(hour=11), None, _NOW
            )
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.starts_at == _START
        assert _audits(session) == 1


def test_reschedule_over_http(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    start = _future_at(9, 0)
    booked = _post(api, patient_id, clinician_id, type_id, start)
    appointment_id = str(booked.json()["id"])
    moved_to = _future_at(9, 15)
    moved = api.post(
        f"/appointments/{appointment_id}/reschedule",
        cookies=_cookie(api),
        json={"starts_at": moved_to.isoformat()},
    )
    assert moved.status_code == 200
    assert moved.json()["starts_at"] == moved_to.isoformat()
    assert moved.json()["ends_at"] == (moved_to + timedelta(minutes=30)).isoformat()
    assert moved.json()["patient"]["id"] == patient_id
    extra = api.post(
        f"/appointments/{appointment_id}/reschedule",
        cookies=_cookie(api),
        json={"starts_at": _future_at(10, 0).isoformat(), "note": "nope"},
    )
    assert extra.status_code == 422
    assert "body.note" in extra.json()["error"]["message"]
    assert "nope" not in extra.text
    missing = str(uuid4())
    unknown = api.post(
        f"/appointments/{missing}/reschedule",
        cookies=_cookie(api),
        json={"starts_at": _future_at(10, 0).isoformat()},
    )
    assert unknown.status_code == 404
    assert missing not in unknown.text


def test_http_conflicts_and_roles(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    other = _second_clinician()
    first = _post(api, patient_id, clinician_id, type_id, _future_at(10, 0))
    second_patient = api.post(
        "/patients", cookies=_cookie(api), json={"full_name": "Sample Bea", "phone": "9000000002"}
    ).json()["id"]
    second = _post(api, second_patient, other, type_id, _future_at(11, 0))
    same_patient = _post(api, patient_id, other, type_id, _future_at(12, 0))
    taken = api.post(
        f"/appointments/{second.json()['id']}/reschedule",
        cookies=_cookie(api),
        json={"starts_at": _future_at(10, 0).isoformat(), "clinician_id": clinician_id},
    )
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "slot_taken"
    busy = api.post(
        f"/appointments/{same_patient.json()['id']}/reschedule",
        cookies=_cookie(api),
        json={"starts_at": _future_at(10, 0).isoformat(), "clinician_id": other},
    )
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "patient_busy"
    _set_status(UUID(str(first.json()["id"])), "completed")
    stuck = api.post(
        f"/appointments/{first.json()['id']}/reschedule",
        cookies=_cookie(api),
        json={"starts_at": _future_at(12, 0).isoformat()},
    )
    assert stuck.status_code == 409
    assert stuck.json()["error"]["code"] == "invalid_status"
    inventory = {"dc_session": login(api, "inventory@x.test")}
    forbidden = api.post(
        f"/appointments/{second.json()['id']}/reschedule",
        cookies=inventory,
        json={"starts_at": _future_at(12, 0).isoformat()},
    )
    assert forbidden.status_code == 403
    api.cookies.clear()
    anonymous = api.post(
        f"/appointments/{second.json()['id']}/reschedule",
        json={"starts_at": _future_at(12, 0).isoformat()},
    )
    assert anonymous.status_code == 401


def test_another_clinic_cannot_move_or_assign_its_clinician(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    booked = _post(api, patient_id, clinician_id, type_id, _future_at(10, 0))
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
        other_clinician = create_user(
            session,
            other.id,
            "other-clinician@x.test",
            "Other Clinician",
            "synthetic-password-marker",
            ["clinician"],
        )
        session.commit()
        other_clinician_id = str(other_clinician.id)
    cookie = {"dc_session": login(api, "other@x.test")}
    hidden = api.post(
        f"/appointments/{appointment_id}/reschedule",
        cookies=cookie,
        json={"starts_at": _future_at(11, 0).isoformat()},
    )
    assert hidden.status_code == 404
    stolen = api.post(
        f"/appointments/{appointment_id}/reschedule",
        cookies=_cookie(api),
        json={"starts_at": _future_at(11, 0).isoformat(), "clinician_id": other_clinician_id},
    )
    assert stolen.status_code == 422
    assert "body.clinician_id" in stolen.json()["error"]["message"]
    assert other_clinician_id not in stolen.text


def test_availability_requires_exactly_one_of_type_or_visit(api: TestClient) -> None:
    _patient_id, clinician_id, type_id = _ids(api)
    day = _future_at(10, 0).date().isoformat()
    base = {"date": day, "clinician_id": clinician_id}
    neither = api.get("/appointments/availability", cookies=_cookie(api), params=base)
    assert neither.status_code == 422
    assert "query.appointment_type_id" in neither.json()["error"]["message"]
    missing = str(uuid4())
    both = api.get(
        "/appointments/availability",
        cookies=_cookie(api),
        params={**base, "appointment_type_id": type_id, "reschedule_appointment_id": missing},
    )
    assert both.status_code == 422
    assert "query.reschedule_appointment_id" in both.json()["error"]["message"]
    assert missing not in both.text


def test_the_route_names_its_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    roles = _roles(create_app())
    assert roles[("POST", "/appointments/{appointment_id}/reschedule")] == set(APPOINTMENT_ROLES)


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
        patient = register_patient(session, clinic.id, actor.id, "Sample Ada", "9000000001", None)
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        return clinic.id, actor.id, clinician.id, patient.id, consultation.id


def _clinician(clinic_id: UUID, email: str, name: str) -> UUID:
    with Session(get_engine()) as session:
        user = create_user(
            session, clinic_id, email, name, "synthetic-password-marker", ["clinician"]
        )
        session.commit()
        return user.id


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


def _audits(session: Session) -> int:
    count = session.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "appointment")
    )
    return int(count or 0)


def _ids(api: TestClient) -> tuple[str, str, str]:
    created = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": "Sample Ada", "phone": "9000000001"},
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
        return str(created.json()["id"]), str(clinician.id), str(consultation.id)


def _second_clinician() -> str:
    with Session(get_engine()) as session:
        clinic_id = session.scalars(select(AppUser.clinic_id).limit(1)).one()
        user = create_user(
            session,
            clinic_id,
            "two@x.test",
            "Second Clinician",
            "synthetic-password-marker",
            ["clinician"],
        )
        session.commit()
        return str(user.id)


def _post(
    api: TestClient, patient_id: str, clinician_id: str, type_id: str, start: datetime
) -> Response:
    return cast(
        Response,
        api.post(
            "/appointments",
            cookies=_cookie(api),
            json={
                "patient_id": patient_id,
                "clinician_id": clinician_id,
                "appointment_type_id": type_id,
                "starts_at": start.isoformat(),
            },
        ),
    )


def _set_status(appointment_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        row.status = status
        session.commit()


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _future_at(hour: int, minute: int) -> datetime:
    now = datetime.now(_ZONE)
    day = now.date() + timedelta(days=1)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=_ZONE)


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
