"""GET /follow-ups: due and all views, order, paging, clinic scope, inactive patients."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.app_user import AppUser
from dentacircle.services.follow_up_service import list_follow_ups
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api

_ZONE = ZoneInfo("Asia/Kolkata")
_ROLES = ("receptionist", "clinician", "clinic_admin", "inventory_admin")
_EMAILS = {
    "receptionist": "receptionist@x.test",
    "clinician": "clinician@x.test",
    "clinic_admin": "admin@x.test",
    "inventory_admin": "inventory@x.test",
}
_QUEUE_FIELDS = {"id", "status", "due_on", "timing", "patient"}
_PATIENT_FIELDS = {"id", "display_id", "full_name", "phone"}
_MARKER = "follow-up-queue-marker"


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_due_view_is_the_default_and_hides_future_and_booked(api: TestClient) -> None:
    today = _today()
    overdue_id = _follow_up(api, "Sample Ada", "9000000001", today - timedelta(days=1))
    due_id = _follow_up(api, "Sample Bea", "9000000002", today)
    upcoming_id = _follow_up(api, "Sample Cyd", "9000000003", today + timedelta(days=2))
    booked_id = _follow_up(api, "Sample Dee", "9000000004", today, status="booked")
    contacted_id = _follow_up(api, "Sample Eve", "9000000005", today, status="contacted")
    _follow_up(api, "Sample Fay", "9000000006", today, status="completed")
    _follow_up(api, "Sample Gia", "9000000007", today, status="cancelled")

    cookies = _cookie(api)
    due = api.get("/follow-ups", cookies=cookies)
    assert due.status_code == 200
    body = due.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 3
    ids = [item["id"] for item in body["items"]]
    assert ids == [overdue_id, due_id, contacted_id]
    assert upcoming_id not in ids
    assert booked_id not in ids
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[overdue_id]["timing"] == "overdue"
    assert by_id[due_id]["timing"] == "due_today"
    assert by_id[contacted_id]["timing"] == "due_today"
    assert by_id[due_id]["status"] == "scheduled"
    assert by_id[contacted_id]["status"] == "contacted"
    assert set(by_id[due_id]) == _QUEUE_FIELDS
    assert set(by_id[due_id]["patient"]) == _PATIENT_FIELDS
    assert by_id[due_id]["patient"]["full_name"] == "Sample Bea"
    assert by_id[due_id]["patient"]["phone"] == "9000000002"
    assert by_id[due_id]["patient"]["display_id"] == "P-0002"
    assert "T" not in by_id[due_id]["due_on"]

    explicit = api.get("/follow-ups", cookies=cookies, params={"view": "due"})
    assert [item["id"] for item in explicit.json()["items"]] == ids


def test_all_open_includes_booked_and_upcoming_and_orders_by_due_then_number(
    api: TestClient,
) -> None:
    today = _today()
    later = today + timedelta(days=3)
    first = _follow_up(api, "Sample Ada", "9000000001", later)
    second = _follow_up(api, "Sample Bea", "9000000002", later)
    overdue = _follow_up(api, "Sample Cyd", "9000000003", today - timedelta(days=2))
    booked = _follow_up(api, "Sample Dee", "9000000004", today + timedelta(days=1), status="booked")
    _follow_up(api, "Sample Eve", "9000000005", today, status="completed")

    listed = api.get("/follow-ups", cookies=_cookie(api), params={"view": "all"})
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert listed.json()["total"] == 4
    assert [item["id"] for item in items] == [overdue, booked, first, second]
    assert items[0]["timing"] == "overdue"
    assert items[1]["timing"] == "upcoming"
    assert items[1]["status"] == "booked"
    assert items[2]["patient"]["display_id"] == "P-0001"
    assert items[3]["patient"]["display_id"] == "P-0002"


def test_paging_matches_the_patient_list(api: TestClient) -> None:
    today = _today()
    first = _follow_up(api, "Sample Ada", "9000000001", today)
    second = _follow_up(api, "Sample Bea", "9000000002", today)
    cookies = _cookie(api)
    page = api.get("/follow-ups", cookies=cookies, params={"page": 2, "page_size": 1})
    assert page.status_code == 200
    assert page.json()["page"] == 2
    assert page.json()["page_size"] == 1
    assert page.json()["total"] == 2
    assert [item["id"] for item in page.json()["items"]] == [second]
    first_page = api.get("/follow-ups", cookies=cookies, params={"page": 1, "page_size": 1})
    assert [item["id"] for item in first_page.json()["items"]] == [first]
    wide = api.get("/follow-ups", cookies=cookies, params={"page_size": 100})
    assert wide.json()["page_size"] == 100
    assert wide.json()["total"] == 2


def test_another_clinic_and_inactive_patients_are_left_out(api: TestClient) -> None:
    today = _today()
    own = _follow_up(api, "Sample Ada", "9000000001", today)
    inactive_patient = _patient(api, "Sample Bea", "9000000002")
    inactive_follow_up = _follow_up_for(api, inactive_patient, today)
    _set_inactive(UUID(inactive_patient))
    other = _other_clinic_follow_up(today)

    listed = api.get("/follow-ups", cookies=_cookie(api), params={"view": "all"})
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()["items"]]
    assert ids == [own]
    assert inactive_follow_up not in ids
    assert other not in ids
    assert _MARKER not in listed.text


def test_bad_view_page_and_page_size_are_422(api: TestClient) -> None:
    cookies = _cookie(api)
    cases = [
        {"view": "open"},
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
    ]
    for params in cases:
        response = api.get("/follow-ups", cookies=cookies, params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_roles_on_the_list_and_no_session(api: TestClient) -> None:
    today = _today()
    follow_up_id = _follow_up(api, "Sample Ada", "9000000001", today)
    for role in _ROLES:
        response = api.get("/follow-ups", cookies=_cookie(api, _EMAILS[role]))
        if role == "inventory_admin":
            assert response.status_code == 403
            assert follow_up_id not in response.text
        else:
            assert response.status_code == 200
            assert response.json()["items"][0]["id"] == follow_up_id
    api.cookies.clear()
    anonymous = api.get("/follow-ups")
    assert anonymous.status_code == 401


def test_list_timing_uses_the_clinic_local_day_not_utc(api: TestClient) -> None:
    today = _today()
    follow_up_id = _follow_up(api, "Sample Ada", "9000000001", today)
    utc_evening = datetime(today.year, today.month, today.day, 20, 0, tzinfo=UTC)
    clinic_id = _clinic_id()
    with Session(get_engine()) as session:
        page = list_follow_ups(session, clinic_id, "all", 1, 20, utc_evening)
    assert page.items[0].id == UUID(follow_up_id)
    assert utc_evening.astimezone(_ZONE).date() == today + timedelta(days=1)
    assert page.items[0].timing == "overdue"


def _today() -> date:
    return datetime.now(UTC).astimezone(_ZONE).date()


def _follow_up(
    api: TestClient,
    name: str,
    phone: str,
    due_on: date,
    status: str = "scheduled",
) -> str:
    return _follow_up_for(api, _patient(api, name, phone), due_on, status)


def _follow_up_for(
    api: TestClient, patient_id: str, due_on: date, status: str = "scheduled"
) -> str:
    today = _today()
    create_on = today if due_on < today else due_on
    created = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": create_on.isoformat()},
    )
    assert created.status_code == 201
    follow_up_id = str(created.json()["follow_up"]["id"])
    if due_on != create_on or status != "scheduled":
        _update_follow_up(UUID(follow_up_id), due_on, status)
    return follow_up_id


def _patient(api: TestClient, name: str, phone: str) -> str:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": name, "phone": phone},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _update_follow_up(follow_up_id: UUID, due_on: date, status: str) -> None:
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE follow_up SET due_on = :due_on, status = :status WHERE id = :id"),
            {"due_on": due_on, "status": status, "id": follow_up_id},
        )
        session.commit()


def _set_inactive(patient_id: UUID) -> None:
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        set_patient_status(session, actor.clinic_id, actor.id, patient_id, "inactive")
        session.commit()


def _other_clinic_follow_up(due_on: date) -> str:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Other Clinic")
        actor = create_user(
            session,
            clinic.id,
            "other-queue@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, _MARKER, "9000000099", None)
        session.commit()
        patient_id = patient.id
        clinic_id = clinic.id
        actor_id = actor.id
    from dentacircle.services.follow_up_service import create_manual_follow_up

    with Session(get_engine()) as session:
        created = create_manual_follow_up(
            session, clinic_id, actor_id, patient_id, due_on, datetime.now(UTC)
        )
        session.commit()
        return str(created.id)


def _clinic_id() -> UUID:
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        return actor.clinic_id


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}
