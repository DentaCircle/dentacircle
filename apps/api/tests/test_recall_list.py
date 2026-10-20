"""GET /recalls: due and all views, order, paging, clinic scope, and separation."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.services.follow_up_service import list_follow_ups
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from dentacircle.services.recall_service import list_recalls
from tests.patient_harness import login, patient_api

_ZONE = ZoneInfo("Asia/Kolkata")
_ROLES = ("receptionist", "clinician", "clinic_admin", "inventory_admin")
_EMAILS = {
    "receptionist": "receptionist@x.test",
    "clinician": "clinician@x.test",
    "clinic_admin": "admin@x.test",
    "inventory_admin": "inventory@x.test",
}
_ITEM_FIELDS = {
    "id",
    "status",
    "due_on",
    "timing",
    "last_visit_on",
    "recall_type",
    "patient",
}
_PATIENT_FIELDS = {"id", "display_id", "full_name", "phone"}
_MARKER = "recall-list-marker"


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    _SLOT["n"] = 0
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


_SLOT = {"n": 0}


def test_due_view_is_the_default_and_hides_future_booked_and_closed(api: TestClient) -> None:
    today = _today()
    overdue_id, overdue_visit = _recall(api, "Sample Ada", "9000000001", today - timedelta(days=1))
    due_id, _due_visit = _recall(api, "Sample Bea", "9000000002", today)
    upcoming_id, _upcoming_visit = _recall(
        api, "Sample Cyd", "9000000003", today + timedelta(days=2)
    )
    booked_id, _booked_visit = _recall(api, "Sample Dee", "9000000004", today, status="booked")
    contacted_id, _contacted_visit = _recall(
        api, "Sample Eve", "9000000005", today, status="contacted"
    )
    _recall(api, "Sample Fay", "9000000006", today, status="completed")
    _recall(api, "Sample Gia", "9000000007", today, status="cancelled")

    cookies = _cookie(api)
    due = api.get("/recalls", cookies=cookies)
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
    assert set(by_id[due_id]) == _ITEM_FIELDS
    assert set(by_id[due_id]["patient"]) == _PATIENT_FIELDS
    assert set(by_id[due_id]["recall_type"]) == {"id", "name"}
    assert by_id[due_id]["recall_type"]["name"] == "Scaling"
    assert by_id[due_id]["patient"]["full_name"] == "Sample Bea"
    assert by_id[due_id]["patient"]["display_id"] == "P-0002"
    assert by_id[overdue_id]["last_visit_on"] == overdue_visit
    assert "T" not in by_id[due_id]["due_on"]

    explicit = api.get("/recalls", cookies=cookies, params={"view": "due"})
    assert [item["id"] for item in explicit.json()["items"]] == ids


def test_all_open_includes_booked_and_upcoming_and_orders_by_due_then_number(
    api: TestClient,
) -> None:
    today = _today()
    later = today + timedelta(days=3)
    first, _first_visit = _recall(api, "Sample Ada", "9000000001", later)
    second, _second_visit = _recall(api, "Sample Bea", "9000000002", later)
    overdue, _overdue_visit = _recall(api, "Sample Cyd", "9000000003", today - timedelta(days=2))
    booked, _booked_visit = _recall(
        api, "Sample Dee", "9000000004", today + timedelta(days=1), status="booked"
    )
    _recall(api, "Sample Eve", "9000000005", today, status="completed")

    listed = api.get("/recalls", cookies=_cookie(api), params={"view": "all"})
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert listed.json()["total"] == 4
    assert [item["id"] for item in items] == [overdue, booked, first, second]
    assert items[1]["status"] == "booked"
    assert items[1]["timing"] == "upcoming"
    assert items[2]["patient"]["display_id"] == "P-0001"
    assert items[3]["patient"]["display_id"] == "P-0002"


def test_paging_matches_follow_ups(api: TestClient) -> None:
    today = _today()
    first, _first_visit = _recall(api, "Sample Ada", "9000000001", today)
    second, _second_visit = _recall(api, "Sample Bea", "9000000002", today)
    cookies = _cookie(api)
    page = api.get("/recalls", cookies=cookies, params={"page": 2, "page_size": 1})
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert [item["id"] for item in page.json()["items"]] == [second]
    first_page = api.get("/recalls", cookies=cookies, params={"page": 1, "page_size": 1})
    assert [item["id"] for item in first_page.json()["items"]] == [first]
    wide = api.get("/recalls", cookies=cookies, params={"page_size": 100})
    assert wide.json()["page_size"] == 100


def test_another_clinic_and_inactive_patients_are_left_out(api: TestClient) -> None:
    today = _today()
    own, _own_visit = _recall(api, "Sample Ada", "9000000001", today)
    inactive_patient = _patient(api, "Sample Bea", "9000000002")
    hidden, _hidden_visit = _recall_for(api, inactive_patient, today)
    _set_inactive(UUID(inactive_patient))
    other = _other_clinic_recall(today)

    listed = api.get("/recalls", cookies=_cookie(api), params={"view": "all"})
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()["items"]]
    assert ids == [own]
    assert hidden not in ids
    assert other not in ids
    assert _MARKER not in listed.text


def test_recalls_and_follow_ups_stay_on_separate_lists(api: TestClient) -> None:
    today = _today()
    patient_id = _patient(api, "Sample Ada", "9000000001")
    recall_id, _visit = _recall_for(api, patient_id, today)
    created = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": today.isoformat()},
    )
    assert created.status_code == 201
    follow_up_id = created.json()["follow_up"]["id"]
    cookies = _cookie(api)
    recalls = api.get("/recalls", cookies=cookies, params={"view": "all"})
    follow_ups = api.get("/follow-ups", cookies=cookies, params={"view": "all"})
    assert [item["id"] for item in recalls.json()["items"]] == [recall_id]
    assert [item["id"] for item in follow_ups.json()["items"]] == [follow_up_id]


def test_bad_view_page_and_page_size_are_422_after_the_session_and_role(api: TestClient) -> None:
    api.cookies.clear()
    anonymous = api.get("/recalls", params={"view": "open"})
    assert anonymous.status_code == 401
    denied = api.get("/recalls", cookies=_cookie(api, "inventory@x.test"), params={"page": 0})
    assert denied.status_code == 403
    cookies = _cookie(api)
    for params in ({"view": "open"}, {"page": 0}, {"page_size": 0}, {"page_size": 101}):
        response = api.get("/recalls", cookies=cookies, params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_roles_on_the_list_and_no_session(api: TestClient) -> None:
    today = _today()
    recall_id, _visit = _recall(api, "Sample Ada", "9000000001", today)
    for role in _ROLES:
        response = api.get("/recalls", cookies=_cookie(api, _EMAILS[role]))
        if role == "inventory_admin":
            assert response.status_code == 403
            assert recall_id not in response.text
        else:
            assert response.status_code == 200
            assert response.json()["items"][0]["id"] == recall_id
    api.cookies.clear()
    assert api.get("/recalls").status_code == 401


def test_list_timing_uses_the_clinic_local_day_not_utc(api: TestClient) -> None:
    today = _today()
    recall_id, _visit = _recall(api, "Sample Ada", "9000000001", today)
    utc_evening = datetime(today.year, today.month, today.day, 20, 0, tzinfo=UTC)
    clinic_id = _clinic_id()
    with Session(get_engine()) as session:
        page = list_recalls(session, clinic_id, "all", 1, 20, utc_evening)
        follow_ups = list_follow_ups(session, clinic_id, "all", 1, 20, utc_evening)
    assert page.items[0].id == UUID(recall_id)
    assert utc_evening.astimezone(_ZONE).date() == today + timedelta(days=1)
    assert page.items[0].timing == "overdue"
    assert follow_ups.items == []


def _today() -> date:
    return datetime.now(UTC).astimezone(_ZONE).date()


def _recall(
    api: TestClient, name: str, phone: str, due_on: date, status: str = "scheduled"
) -> tuple[str, str]:
    return _recall_for(api, _patient(api, name, phone), due_on, status)


def _recall_for(
    api: TestClient, patient_id: str, due_on: date, status: str = "scheduled"
) -> tuple[str, str]:
    visit_id, type_id, visit_on = _book(api, patient_id)
    recall_id = str(uuid4())
    with Session(get_engine()) as session:
        visit = session.get(Appointment, UUID(visit_id))
        assert visit is not None
        session.execute(
            text(
                "INSERT INTO recall"
                " (id, clinic_id, patient_id, appointment_type_id, source_appointment_id,"
                "  status, due_on)"
                " VALUES (:id, :clinic_id, :patient_id, :type_id, :visit_id, :status, :due_on)"
            ),
            {
                "id": recall_id,
                "clinic_id": visit.clinic_id,
                "patient_id": patient_id,
                "type_id": type_id,
                "visit_id": visit_id,
                "status": status,
                "due_on": due_on,
            },
        )
        session.commit()
    return recall_id, visit_on


def _book(api: TestClient, patient_id: str) -> tuple[str, str, str]:
    cookies = _cookie(api, "receptionist@x.test")
    types = api.get("/appointment-types", cookies=cookies).json()
    scaling = next(row for row in types if row["name"] == "Scaling")
    clinician_id = api.get("/clinicians", cookies=cookies).json()[0]["id"]
    starts = _next_start()
    created = api.post(
        "/appointments",
        cookies=cookies,
        json={
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "appointment_type_id": scaling["id"],
            "starts_at": starts.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"], scaling["id"], starts.date().isoformat()


def _next_start() -> datetime:
    index = _SLOT["n"]
    _SLOT["n"] += 1
    day = _today() + timedelta(days=1 + index // 4)
    while day.weekday() == 6:
        day += timedelta(days=1)
    hour = 10 + (index % 4) * 2
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=_ZONE)


def _patient(api: TestClient, name: str, phone: str) -> str:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": name, "phone": phone},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _set_inactive(patient_id: UUID) -> None:
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        set_patient_status(session, actor.clinic_id, actor.id, patient_id, "inactive")
        session.commit()


def _other_clinic_recall(due_on: date) -> str:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Other Clinic")
        actor = create_user(
            session,
            clinic.id,
            "other-recall@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, _MARKER, "9000000099", None)
        session.commit()
        clinic_id = clinic.id
        actor_id = actor.id
        patient_id = patient.id
    from dentacircle.services.appointment_service import book_appointment
    from dentacircle.services.appointment_type_service import list_appointment_types

    with Session(get_engine()) as session:
        scaling = next(
            item
            for item in list_appointment_types(session, clinic_id, include_inactive=False)
            if item.name == "Scaling"
        )
        visit = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            actor_id,
            scaling.id,
            _next_start(),
            datetime.now(UTC),
        )
        session.commit()
        visit_id = visit.id
        type_id = scaling.id
    recall_id = str(uuid4())
    with Session(get_engine()) as session:
        session.execute(
            text(
                "INSERT INTO recall"
                " (id, clinic_id, patient_id, appointment_type_id, source_appointment_id,"
                "  status, due_on)"
                " VALUES (:id, :clinic_id, :patient_id, :type_id, :visit_id, 'scheduled', :due_on)"
            ),
            {
                "id": recall_id,
                "clinic_id": clinic_id,
                "patient_id": patient_id,
                "type_id": type_id,
                "visit_id": visit_id,
                "due_on": due_on,
            },
        )
        session.commit()
    return recall_id


def _clinic_id() -> UUID:
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        return actor.clinic_id


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}
