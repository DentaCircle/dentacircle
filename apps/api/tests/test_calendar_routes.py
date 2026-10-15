"""GET /appointments: shape, range rules, roles and tenancy."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4
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
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api
from tests.test_access import iter_api_routes

_ZONE = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_the_list_returns_the_visit_in_clinic_time(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    start = _future_at(10, 0)
    booked = _book(api, patient_id, clinician_id, type_id, start)
    assert booked.status_code == 201
    listed = api.get("/appointments", cookies=_cookie(api), params=_span(start))
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    item = body[0]
    assert item["id"] == booked.json()["id"]
    assert item["starts_at"] == start.isoformat()
    assert item["ends_at"] == (start + timedelta(minutes=30)).isoformat()
    assert item["starts_at"].endswith("+05:30")
    assert item["status"] == "scheduled"
    assert item["patient"] == {
        "id": patient_id,
        "full_name": "Sample Ada",
        "display_id": "P-0001",
    }
    assert item["clinician"]["id"] == clinician_id
    assert item["clinician"]["full_name"] == "Synthetic Person"
    assert item["appointment_type"]["name"] == "Consultation"
    assert "patient_id" not in item


def test_both_days_are_included_and_the_neighbours_are_not(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    monday = _next_weekday(0)
    before = _at(monday, 10, 0)
    first = _at(monday + timedelta(days=1), 10, 0)
    last = _at(monday + timedelta(days=2), 11, 0)
    after = _at(monday + timedelta(days=3), 12, 0)
    for start in (before, first, last, after):
        assert _book(api, patient_id, clinician_id, type_id, start).status_code == 201
    listed = api.get(
        "/appointments",
        cookies=_cookie(api),
        params={"from": first.date().isoformat(), "to": last.date().isoformat()},
    )
    assert listed.status_code == 200
    starts = [item["starts_at"] for item in listed.json()]
    assert starts == [first.isoformat(), last.isoformat()]


def test_cancelled_is_hidden_and_no_show_stays(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    kept = _future_at(10, 0)
    dropped = _future_at(11, 0)
    kept_id = _book(api, patient_id, clinician_id, type_id, kept).json()["id"]
    dropped_id = _book(api, patient_id, clinician_id, type_id, dropped).json()["id"]
    _set_status(dropped_id, "cancelled")
    _set_status(kept_id, "no_show")
    listed = api.get("/appointments", cookies=_cookie(api), params=_span(kept))
    assert [item["id"] for item in listed.json()] == [kept_id]
    assert listed.json()[0]["status"] == "no_show"


def test_an_inactive_patient_is_still_listed(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    start = _future_at(10, 0)
    booked = _book(api, patient_id, clinician_id, type_id, start)
    changed = api.put(
        f"/patients/{patient_id}/status",
        cookies=_cookie(api),
        json={"status": "inactive"},
    )
    assert changed.status_code == 200
    listed = api.get("/appointments", cookies=_cookie(api), params=_span(start))
    assert listed.json()[0]["id"] == booked.json()["id"]
    assert listed.json()[0]["patient"]["full_name"] == "Sample Ada"


def test_the_clinician_filter_and_a_bad_clinician(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    other = _second_clinician()
    start = _future_at(10, 0)
    own = _book(api, patient_id, clinician_id, type_id, start).json()["id"]
    _book(api, patient_id, other, type_id, _future_at(11, 0))
    listed = api.get(
        "/appointments",
        cookies=_cookie(api),
        params={**_span(start), "clinician_id": clinician_id},
    )
    assert [item["id"] for item in listed.json()] == [own]
    missing = str(uuid4())
    rejected = api.get(
        "/appointments",
        cookies=_cookie(api),
        params={**_span(start), "clinician_id": missing},
    )
    assert rejected.status_code == 422
    assert "query.clinician_id" in rejected.json()["error"]["message"]
    assert missing not in rejected.text


def test_a_bad_range_names_the_field_and_hides_the_value(api: TestClient) -> None:
    today = datetime.now(_ZONE).date()
    marker = "not-a-real-date"
    cases = [
        ({"to": today.isoformat()}, "query.from"),
        ({"from": today.isoformat()}, "query.to"),
        ({"from": marker, "to": today.isoformat()}, "query.from"),
        ({"from": today.isoformat(), "to": marker}, "query.to"),
        (
            {"from": today.isoformat(), "to": (today - timedelta(days=1)).isoformat()},
            "query.to",
        ),
        (
            {"from": today.isoformat(), "to": (today + timedelta(days=7)).isoformat()},
            "span_too_long",
        ),
        (
            {
                "from": (today + timedelta(days=366)).isoformat(),
                "to": (today + timedelta(days=366)).isoformat(),
            },
            "beyond_horizon",
        ),
    ]
    for params, expected in cases:
        response = api.get("/appointments", cookies=_cookie(api), params=params)
        assert response.status_code == 422
        message = response.json()["error"]["message"]
        assert expected in message
        assert marker not in response.text
        for value in params.values():
            assert value not in response.text


def test_past_dates_are_allowed(api: TestClient) -> None:
    yesterday = (datetime.now(_ZONE).date() - timedelta(days=1)).isoformat()
    response = api.get(
        "/appointments",
        cookies=_cookie(api),
        params={"from": yesterday, "to": yesterday},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_the_list_writes_nothing(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    start = _future_at(10, 0)
    assert _book(api, patient_id, clinician_id, type_id, start).status_code == 201
    before_rows, before_audits = _counts()
    listed = api.get("/appointments", cookies=_cookie(api), params=_span(start))
    assert listed.status_code == 200
    assert _counts() == (before_rows, before_audits)


@pytest.mark.parametrize("email", ["receptionist@x.test", "clinician@x.test", "admin@x.test"])
def test_the_three_roles_can_list(api: TestClient, email: str) -> None:
    today = datetime.now(_ZONE).date().isoformat()
    response = api.get(
        "/appointments",
        cookies=_cookie(api, email),
        params={"from": today, "to": today},
    )
    assert response.status_code == 200


def test_inventory_admin_and_a_missing_session_are_rejected(api: TestClient) -> None:
    today = datetime.now(_ZONE).date().isoformat()
    params = {"from": today, "to": today}
    inventory = {"dc_session": login(api, "inventory@x.test")}
    forbidden = api.get("/appointments", params=params, cookies=inventory)
    assert forbidden.status_code == 403
    api.cookies.clear()
    anonymous = api.get("/appointments", params=params)
    assert anonymous.status_code == 401


def test_another_clinic_cannot_see_the_visit(api: TestClient) -> None:
    patient_id, clinician_id, type_id = _ids(api)
    start = _future_at(10, 0)
    assert _book(api, patient_id, clinician_id, type_id, start).status_code == 201
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
    listed = api.get("/appointments", cookies=cookie, params=_span(start))
    assert listed.status_code == 200
    assert listed.json() == []
    assert patient_id not in listed.text


def test_the_list_route_names_its_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    roles = _roles(create_app())
    assert roles[("GET", "/appointments")] == set(APPOINTMENT_ROLES)


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
    api: TestClient, patient_id: str, clinician_id: str, type_id: str, starts_at: datetime
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
                "starts_at": starts_at.isoformat(),
            },
        ),
    )


def _set_status(appointment_id: str, status: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(Appointment, UUID(appointment_id))
        assert row is not None
        row.status = status
        session.commit()


def _span(start: datetime) -> dict[str, str]:
    day = start.date().isoformat()
    return {"from": day, "to": day}


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _next_weekday(weekday: int) -> datetime:
    day = datetime.now(_ZONE).date() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, tzinfo=_ZONE)


def _at(day: datetime, hour: int, minute: int) -> datetime:
    return day.replace(hour=hour, minute=minute)


def _future_at(hour: int, minute: int, days: int = 1) -> datetime:
    now = datetime.now(_ZONE)
    day = now.date() + timedelta(days=days)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=_ZONE)


def _counts() -> tuple[int, int]:
    with Session(get_engine()) as session:
        rows = session.scalar(select(func.count()).select_from(Appointment))
        audits = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "appointment")
        )
    return int(rows or 0), int(audits or 0)


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
