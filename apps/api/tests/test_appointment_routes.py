"""Book, free times and upcoming visits over HTTP."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.appointment import APPOINTMENT_ROLES
from dentacircle.main import create_app
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes

_ZONE = ZoneInfo("Asia/Kolkata")
_PHONE = "9000000001"


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_booking_returns_the_visit_in_clinic_time(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    start = _future_at(10, 0)
    response = _book(api, patient_id, clinician_id, type_id, start)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "scheduled"
    assert body["patient_id"] == patient_id
    assert body["starts_at"] == start.isoformat()
    assert body["ends_at"] == (start + timedelta(minutes=30)).isoformat()
    assert body["starts_at"].endswith("+05:30")
    assert body["clinician"]["id"] == clinician_id
    assert body["appointment_type"]["name"] == "Consultation"
    listed = api.get(f"/patients/{patient_id}/appointments", cookies=_cookie(api))
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [body["id"]]


def test_extra_fields_are_rejected_and_not_echoed(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    marker = "must-not-echo"
    response = api.post(
        "/appointments",
        cookies=_cookie(api),
        json={
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": _future_at(10, 0).isoformat(),
            "notes": marker,
        },
    )
    assert response.status_code == 422
    assert "body.notes" in response.json()["error"]["message"]
    assert marker not in response.text
    assert _appointment_count() == 0


def test_each_bad_start_names_the_field_and_hides_the_value(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    day = _future_at(10, 0).date().isoformat()
    cases = [
        (f"{day}T10:00:00", "timezone_naive"),
        (_past().isoformat(), "past"),
        (_future_at(10, 0, days=366).isoformat(), "beyond_horizon"),
        (_future_at(8, 0).isoformat(), "outside_hours"),
        (_future_at(10, 7).isoformat(), "not_on_grid"),
    ]
    for starts_at, code in cases:
        response = _book(api, patient_id, clinician_id, type_id, starts_at)
        assert response.status_code == 422
        message = response.json()["error"]["message"]
        assert "body.starts_at" in message
        assert code in message
        assert starts_at not in response.text
    assert _appointment_count() == 0


def test_each_bad_party_names_the_field(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    start = _future_at(10, 0).isoformat()
    missing = str(uuid4())
    cases = [
        {"patient_id": missing, "clinician_id": clinician_id, "appointment_type_id": type_id},
        {"patient_id": patient_id, "clinician_id": missing, "appointment_type_id": type_id},
        {"patient_id": patient_id, "clinician_id": clinician_id, "appointment_type_id": missing},
    ]
    fields = ["patient_id", "clinician_id", "appointment_type_id"]
    for body, field in zip(cases, fields, strict=True):
        response = api.post(
            "/appointments",
            cookies=_cookie(api),
            json={**body, "starts_at": start},
        )
        assert response.status_code == 422
        assert f"body.{field}" in response.json()["error"]["message"]
        assert missing not in response.text
    assert _appointment_count() == 0


def test_availability_names_a_bad_date_clinician_or_type(api: TestClient) -> None:
    _patient_id, clinician_id, type_id = _ids(api)
    yesterday = (datetime.now(_ZONE).date() - timedelta(days=1)).isoformat()
    later = (datetime.now(_ZONE).date() + timedelta(days=366)).isoformat()
    missing = str(uuid4())
    cases = [
        {
            "date": yesterday,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "field": "date",
        },
        {
            "date": later,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "field": "date",
        },
        {
            "date": _future_at(10, 0).date().isoformat(),
            "clinician_id": missing,
            "appointment_type_id": type_id,
            "field": "clinician_id",
        },
        {
            "date": _future_at(10, 0).date().isoformat(),
            "clinician_id": clinician_id,
            "appointment_type_id": missing,
            "field": "appointment_type_id",
        },
    ]
    for case in cases:
        field = str(case.pop("field"))
        response = api.get("/appointments/availability", cookies=_cookie(api), params=case)
        assert response.status_code == 422
        assert f"query.{field}" in response.json()["error"]["message"]
        assert missing not in response.text


def test_a_closed_day_and_a_free_slot(api: TestClient) -> None:
    _patient_id, clinician_id, type_id = _ids(api)
    sunday = _next_sunday()
    closed = api.get(
        "/appointments/availability",
        cookies=_cookie(api),
        params={
            "date": sunday.isoformat(),
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
        },
    )
    assert closed.status_code == 200
    assert closed.json()["is_open"] is False
    assert closed.json()["slots"] == []
    open_day = api.get(
        "/appointments/availability",
        cookies=_cookie(api),
        params={
            "date": _future_at(10, 0).date().isoformat(),
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
        },
    )
    assert open_day.status_code == 200
    assert open_day.json()["is_open"] is True
    assert open_day.json()["slots"][0]["starts_at"].endswith("+05:30")


def test_a_taken_slot_is_409_and_a_busy_patient_is_409(api: TestClient) -> None:
    first, clinician_id, type_id = _ids(api)
    second = _patient(api, "Sample Bea", "9000000002")
    start = _future_at(10, 0)
    assert _book(api, first, clinician_id, type_id, start).status_code == 201
    taken = _book(api, second, clinician_id, type_id, start)
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "slot_taken"
    assert start.isoformat() not in taken.text
    other_clinician = _second_clinician()
    busy = _book(api, first, other_clinician, type_id, start)
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "patient_busy"
    assert _appointment_count() == 1
    with Session(get_engine()) as session:
        audits = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "appointment")
        )
    assert audits == 1


def test_an_unknown_patient_upcoming_list_is_404(api: TestClient) -> None:
    missing = str(uuid4())
    response = api.get(f"/patients/{missing}/appointments", cookies=_cookie(api))
    assert response.status_code == 404
    assert missing not in response.text


def test_another_clinic_cannot_book_or_see_the_visit(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    start = _future_at(11, 0)
    assert _book(api, patient_id, clinician_id, type_id, start).status_code == 201
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        actor = create_user(
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
        other_patient = register_patient(
            session, other.id, actor.id, "Sample Bea", "9000000002", None
        )
        other_type = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == other.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        other_patient_id = str(other_patient.id)
        other_clinician_id = str(other_clinician.id)
        other_type_id = str(other_type.id)
    cookie = {"dc_session": login(api, "other@x.test")}
    stolen = api.post(
        "/appointments",
        cookies=cookie,
        json={
            "patient_id": patient_id,
            "clinician_id": other_clinician_id,
            "appointment_type_id": other_type_id,
            "starts_at": start.isoformat(),
        },
    )
    assert stolen.status_code == 422
    assert "body.patient_id" in stolen.json()["error"]["message"]
    assert patient_id not in stolen.text
    hidden = api.get(f"/patients/{patient_id}/appointments", cookies=cookie)
    assert hidden.status_code == 404
    free = api.get(
        "/appointments/availability",
        cookies=cookie,
        params={
            "date": start.date().isoformat(),
            "clinician_id": other_clinician_id,
            "appointment_type_id": other_type_id,
        },
    )
    assert free.status_code == 200
    assert any(slot["starts_at"] == start.isoformat() for slot in free.json()["slots"])
    blocked = api.get(
        "/appointments/availability",
        cookies=_cookie(api),
        params={
            "date": start.date().isoformat(),
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
        },
    )
    assert all(slot["starts_at"] != start.isoformat() for slot in blocked.json()["slots"])
    # The other clinic's patient is not visible as a way to book ours.
    assert other_patient_id not in stolen.text


@pytest.mark.parametrize("email", ["receptionist@x.test", "clinician@x.test", "admin@x.test"])
def test_the_three_roles_can_book(api: TestClient, email: str) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    # Spread the three bookings so they do not take the same slot.
    hour = {"receptionist@x.test": 10, "clinician@x.test": 11, "admin@x.test": 12}[email]
    response = api.post(
        "/appointments",
        cookies=_cookie(api, email),
        json={
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": _future_at(hour, 0).isoformat(),
        },
    )
    assert response.status_code == 201


def test_inventory_admin_and_a_missing_session_are_rejected(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    body = {
        "patient_id": patient_id,
        "clinician_id": clinician_id,
        "appointment_type_id": type_id,
        "starts_at": _future_at(10, 0).isoformat(),
    }
    params = {
        "date": _future_at(10, 0).date().isoformat(),
        "clinician_id": clinician_id,
        "appointment_type_id": type_id,
    }
    inventory = {"dc_session": login(api, "inventory@x.test")}
    for cookies in (inventory, None):
        if cookies is None:
            api.cookies.clear()
        booked = api.post("/appointments", json=body, cookies=cookies)
        listed = api.get("/appointments/availability", params=params, cookies=cookies)
        upcoming = api.get(f"/patients/{patient_id}/appointments", cookies=cookies)
        expected = 403 if cookies is not None else 401
        assert booked.status_code == expected
        assert listed.status_code == expected
        assert upcoming.status_code == expected
    assert _appointment_count() == 0


def test_the_routes_list_their_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    roles = _roles(create_app())
    assert roles[("GET", "/appointments/availability")] == set(APPOINTMENT_ROLES)
    assert roles[("POST", "/appointments")] == set(APPOINTMENT_ROLES)
    assert roles[("GET", "/patients/{patient_id}/appointments")] == set(APPOINTMENT_ROLES)


def _ids(api: TestClient) -> tuple[str, str, str]:
    patient_id = _patient(api, "Sample Ada", _PHONE)
    with Session(get_engine()) as session:
        clinician = session.scalars(
            select(AppUser).where(AppUser.email == "clinician@x.test")
        ).one()
        clinic_id = clinician.clinic_id
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic_id)
            )
            if row.name == "Consultation"
        )
        return patient_id, str(clinician.id), str(consultation.id)


def _patient(api: TestClient, name: str, phone: str) -> str:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": name, "phone": phone},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


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


def _book(
    api: TestClient,
    patient_id: str,
    clinician_id: str,
    type_id: str,
    starts_at: datetime | str,
) -> Response:
    text = starts_at.isoformat() if isinstance(starts_at, datetime) else starts_at
    return cast(
        Response,
        api.post(
            "/appointments",
            cookies=_cookie(api),
            json={
                "patient_id": patient_id,
                "clinician_id": clinician_id,
                "appointment_type_id": type_id,
                "starts_at": text,
            },
        ),
    )


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _future_at(hour: int, minute: int, days: int = 1) -> datetime:
    now = datetime.now(_ZONE)
    day = now.date() + timedelta(days=days)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=_ZONE)


def _past() -> datetime:
    day = datetime.now(_ZONE).date() - timedelta(days=1)
    return datetime(day.year, day.month, day.day, 10, 0, tzinfo=_ZONE)


def _next_sunday() -> date:
    day = datetime.now(_ZONE).date() + timedelta(days=1)
    while day.weekday() != 6:
        day += timedelta(days=1)
    return day


def _appointment_count() -> int:
    with Session(get_engine()) as session:
        count = session.scalar(select(func.count()).select_from(Appointment))
    return int(count or 0)


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
