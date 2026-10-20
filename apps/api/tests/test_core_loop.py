"""The M3 loop through the HTTP routes: follow-up, recall, queues, release, and timeline."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import TypedDict, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.recall import add_months
from dentacircle.domain.timeline import TIMELINE_KINDS
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import PASSWORD, login, patient_api
from tests.support import CLINIC_ZONE, next_open_slot, place_visit_today, post_visit_status

# Newest first, after the Scaling visit, the follow-up visit, and the recall visit.
_LOOP_KINDS = [
    "recall_created",
    "recall_completed",
    "follow_up_updated",
    "visit_completed",
    "visit_started",
    "visit_arrived",
    "recall_booked",
    "visit_booked",
    "recall_contacted",
    "follow_up_created",
    "follow_up_completed",
    "visit_completed",
    "visit_started",
    "visit_arrived",
    "follow_up_booked",
    "visit_booked",
    "follow_up_contacted",
    "recall_created",
    "follow_up_created",
    "visit_completed",
    "care_session_recorded",
    "care_item_started",
    "care_item_completed",
    "care_item_added",
    "care_item_added",
    "visit_started",
    "visit_arrived",
    "visit_booked",
    "patient_registered",
]


class _Party(TypedDict):
    id: str


class _TypeName(TypedDict):
    name: str


class _FollowUpRow(TypedDict):
    id: str
    status: str
    timing: str
    patient: _Party


class _RecallRow(TypedDict):
    id: str
    status: str
    due_on: str
    recall_type: _TypeName
    patient: _Party


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_the_scaling_loop_covers_queues_recalls_and_the_timeline(api: TestClient) -> None:
    cookies = _cookie(api)
    clinician_id, types = _desk(api, cookies)
    patient_id = _patient(api, cookies, "9000000091")
    visit_id = _book(api, cookies, patient_id, clinician_id, types["Scaling"])
    _arrive_and_start(api, cookies, visit_id, 10)
    scaling_id, root_canal_id = _plan(api, cookies, patient_id)
    recorded = api.post(
        f"/appointments/{visit_id}/care-session",
        cookies=cookies,
        json={
            "items": [
                {"care_item_id": scaling_id, "status": "completed"},
                {"care_item_id": root_canal_id, "status": "started"},
            ]
        },
    )
    assert recorded.status_code == 201
    post_visit_status(api, cookies, visit_id, "completed")

    today = _today()
    follow_up = _open_follow_up(api, cookies, patient_id)
    assert follow_up["status"] == "scheduled"
    assert follow_up["due_on"] == (today + timedelta(days=7)).isoformat()
    assert follow_up["appointment_id"] == visit_id
    recalls = _recall_items(api, cookies, "all")
    assert len(recalls) == 1
    recall = recalls[0]
    assert recall["status"] == "scheduled"
    assert recall["due_on"] == add_months(today, 6).isoformat()
    assert recall["recall_type"]["name"] == "Scaling"
    assert recall["patient"]["id"] == patient_id

    upcoming = _follow_up_items(api, cookies, "all")
    assert [item["id"] for item in upcoming] == [follow_up["id"]]
    assert upcoming[0]["timing"] == "upcoming"
    assert upcoming[0]["status"] == "scheduled"
    due = _follow_up_items(api, cookies, "due")
    assert follow_up["id"] not in [item["id"] for item in due]
    assert recall["id"] not in [item["id"] for item in upcoming]
    assert recall["id"] not in [item["id"] for item in due]

    _set_due_on(follow_up["id"], today - timedelta(days=1))
    overdue = _follow_up_items(api, cookies, "due")
    assert [item["id"] for item in overdue] == [follow_up["id"]]
    assert overdue[0]["timing"] == "overdue"
    assert overdue[0]["status"] == "scheduled"
    assert recall["id"] not in [item["id"] for item in _follow_up_items(api, cookies, "all")]

    contacted = api.post(f"/follow-ups/{follow_up['id']}/contacted", cookies=cookies)
    assert contacted.status_code == 200
    assert contacted.json()["status"] == "contacted"
    follow_up_visit = _book_from(
        api, cookies, "follow-ups", follow_up["id"], clinician_id, types["Consultation"]
    )
    booked = _open_follow_up(api, cookies, patient_id)
    assert booked["id"] == follow_up["id"]
    assert booked["status"] == "booked"
    _arrive_and_start(api, cookies, follow_up_visit, 11)
    post_visit_status(api, cookies, follow_up_visit, "completed")
    opened = _open_follow_up(api, cookies, patient_id)
    assert opened["id"] != follow_up["id"]
    assert opened["status"] == "scheduled"
    assert opened["due_on"] == (today + timedelta(days=7)).isoformat()

    marked = api.post(f"/recalls/{recall['id']}/contacted", cookies=cookies)
    assert marked.status_code == 200
    assert marked.json()["status"] == "contacted"
    recall_visit = _book_from(api, cookies, "recalls", recall["id"], clinician_id, types["Scaling"])
    stored = api.get(f"/recalls/{recall['id']}", cookies=cookies)
    assert stored.status_code == 200
    assert stored.json()["status"] == "booked"
    _arrive_and_start(api, cookies, recall_visit, 12)
    post_visit_status(api, cookies, recall_visit, "completed")
    closed = api.get(f"/recalls/{recall['id']}", cookies=cookies)
    assert closed.status_code == 404
    renewed = _recall_items(api, cookies, "all")
    assert len(renewed) == 1
    assert renewed[0]["id"] != recall["id"]
    assert renewed[0]["status"] == "scheduled"
    assert renewed[0]["due_on"] == add_months(today, 6).isoformat()
    assert renewed[0]["recall_type"]["name"] == "Scaling"

    timeline = api.get(
        f"/patients/{patient_id}/timeline",
        cookies=cookies,
        params={"page_size": 100},
    )
    assert timeline.status_code == 200
    body = timeline.json()
    kinds = [item["kind"] for item in body["items"]]
    assert kinds == _LOOP_KINDS
    assert body["total"] == len(kinds)
    assert body["page"] == 1
    assert set(kinds) <= set(TIMELINE_KINDS)


def test_a_clinician_date_of_today_is_due_today_with_care_finished(api: TestClient) -> None:
    cookies = _cookie(api)
    clinician_id, types = _desk(api, cookies)
    patient_id = _patient(api, cookies, "9000000092")
    visit_id = _book(api, cookies, patient_id, clinician_id, types["Consultation"])
    _arrive_and_start(api, cookies, visit_id, 10)
    item_id, _other = _plan(api, cookies, patient_id, second=False)
    recorded = api.post(
        f"/appointments/{visit_id}/care-session",
        cookies=cookies,
        json={"items": [{"care_item_id": item_id, "status": "completed"}]},
    )
    assert recorded.status_code == 201
    today = _today().isoformat()
    post_visit_status(api, cookies, visit_id, "completed", follow_up_due_on=today)
    follow_up = _open_follow_up(api, cookies, patient_id)
    assert follow_up["status"] == "scheduled"
    assert follow_up["due_on"] == today
    due = _follow_up_items(api, cookies, "due")
    assert [item["id"] for item in due] == [follow_up["id"]]
    assert due[0]["timing"] == "due_today"
    assert due[0]["patient"]["id"] == patient_id


def test_a_finished_consultation_writes_no_follow_up_and_no_recall(api: TestClient) -> None:
    cookies = _cookie(api)
    clinician_id, types = _desk(api, cookies)
    patient_id = _patient(api, cookies, "9000000093")
    visit_id = _book(api, cookies, patient_id, clinician_id, types["Consultation"])
    _arrive_and_start(api, cookies, visit_id, 10)
    item_id, _other = _plan(api, cookies, patient_id, second=False)
    recorded = api.post(
        f"/appointments/{visit_id}/care-session",
        cookies=cookies,
        json={"items": [{"care_item_id": item_id, "status": "completed"}]},
    )
    assert recorded.status_code == 201
    post_visit_status(api, cookies, visit_id, "completed")
    empty = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
    assert empty.status_code == 200
    assert empty.json()["follow_up"] is None
    assert _recall_items(api, cookies, "all") == []
    timeline = api.get(
        f"/patients/{patient_id}/timeline",
        cookies=cookies,
        params={"page_size": 100},
    )
    assert timeline.status_code == 200
    assert [item["kind"] for item in timeline.json()["items"]] == [
        "visit_completed",
        "care_session_recorded",
        "care_item_completed",
        "care_item_added",
        "visit_started",
        "visit_arrived",
        "visit_booked",
        "patient_registered",
    ]


def test_cancelling_the_booked_visit_returns_the_follow_up_to_due(api: TestClient) -> None:
    cookies = _cookie(api)
    clinician_id, types = _desk(api, cookies)
    patient_id = _patient(api, cookies, "9000000094")
    visit_id = _book(api, cookies, patient_id, clinician_id, types["Consultation"])
    _arrive_and_start(api, cookies, visit_id, 10)
    today = _today().isoformat()
    post_visit_status(api, cookies, visit_id, "completed", follow_up_due_on=today)
    follow_up_id = _open_follow_up(api, cookies, patient_id)["id"]
    contacted = api.post(f"/follow-ups/{follow_up_id}/contacted", cookies=cookies)
    assert contacted.status_code == 200
    booked_visit = _book_from(
        api, cookies, "follow-ups", follow_up_id, clinician_id, types["Consultation"]
    )
    cancelled = api.post(f"/appointments/{booked_visit}/cancel", cookies=cookies)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    released = _open_follow_up(api, cookies, patient_id)
    assert released["id"] == follow_up_id
    assert released["status"] == "contacted"
    due = _follow_up_items(api, cookies, "due")
    assert [item["id"] for item in due] == [follow_up_id]
    assert due[0]["status"] == "contacted"
    assert due[0]["timing"] == "due_today"
    assert due[0]["patient"]["id"] == patient_id


def test_inventory_and_another_clinic_cannot_see_the_loop(api: TestClient) -> None:
    cookies = _cookie(api)
    clinician_id, types = _desk(api, cookies)
    patient_id = _patient(api, cookies, "9000000095")
    visit_id = _book(api, cookies, patient_id, clinician_id, types["Scaling"])
    _arrive_and_start(api, cookies, visit_id, 10)
    post_visit_status(api, cookies, visit_id, "completed", follow_up_due_on=_today().isoformat())
    assert _follow_up_items(api, cookies, "due")
    assert _recall_items(api, cookies, "all")

    inventory = _cookie(api, "inventory@x.test")
    for path in ("/follow-ups", "/recalls", f"/patients/{patient_id}/timeline"):
        refused = api.get(path, cookies=inventory)
        assert refused.status_code == 403
        assert patient_id not in refused.text

    _other_clinic()
    other = _cookie(api, "other@x.test")
    for path, view in (("/follow-ups", "all"), ("/recalls", "all")):
        listed = api.get(path, cookies=other, params={"view": view})
        assert listed.status_code == 200
        assert patient_id not in [item["patient"]["id"] for item in listed.json()["items"]]
    missing = api.get(f"/patients/{patient_id}/timeline", cookies=other)
    assert missing.status_code == 404


def _arrive_and_start(api: TestClient, cookies: dict[str, str], visit_id: str, hour: int) -> None:
    place_visit_today(visit_id, hour)
    post_visit_status(api, cookies, visit_id, "arrived")
    post_visit_status(api, cookies, visit_id, "in_progress")


def _book(
    api: TestClient,
    cookies: dict[str, str],
    patient_id: str,
    clinician_id: str,
    type_id: str,
) -> str:
    start = next_open_slot(api, cookies, clinician_id, type_id, 0)
    response = api.post(
        "/appointments",
        cookies=cookies,
        json={
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": start,
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _book_from(
    api: TestClient,
    cookies: dict[str, str],
    queue: str,
    row_id: str,
    clinician_id: str,
    type_id: str,
) -> str:
    start = next_open_slot(api, cookies, clinician_id, type_id, 0)
    response = api.post(
        f"/{queue}/{row_id}/book",
        cookies=cookies,
        json={
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": start,
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _plan(
    api: TestClient,
    cookies: dict[str, str],
    patient_id: str,
    *,
    second: bool = True,
) -> tuple[str, str | None]:
    plan = api.post(
        f"/patients/{patient_id}/care-plans",
        cookies=cookies,
        json={"title": "Sample plan"},
    )
    assert plan.status_code == 201
    plan_id = plan.json()["id"]
    first = api.post(f"/care-plans/{plan_id}/items", cookies=cookies, json={"name": "Scaling"})
    assert first.status_code == 201
    if not second:
        return str(first.json()["id"]), None
    root = api.post(f"/care-plans/{plan_id}/items", cookies=cookies, json={"name": "Root canal"})
    assert root.status_code == 201
    return str(first.json()["id"]), str(root.json()["id"])


def _open_follow_up(api: TestClient, cookies: dict[str, str], patient_id: str) -> dict[str, str]:
    response = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
    assert response.status_code == 200
    follow_up = response.json()["follow_up"]
    assert follow_up is not None
    return dict(follow_up)


def _follow_up_items(api: TestClient, cookies: dict[str, str], view: str) -> list[_FollowUpRow]:
    response = api.get("/follow-ups", cookies=cookies, params={"view": view, "page_size": 100})
    assert response.status_code == 200
    return cast(list[_FollowUpRow], response.json()["items"])


def _recall_items(api: TestClient, cookies: dict[str, str], view: str) -> list[_RecallRow]:
    response = api.get("/recalls", cookies=cookies, params={"view": view, "page_size": 100})
    assert response.status_code == 200
    return cast(list[_RecallRow], response.json()["items"])


def _set_due_on(follow_up_id: str, due_on: date) -> None:
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE follow_up SET due_on = :due_on WHERE id = :id"),
            {"due_on": due_on, "id": UUID(follow_up_id)},
        )
        session.commit()


def _desk(api: TestClient, cookies: dict[str, str]) -> tuple[str, dict[str, str]]:
    clinicians = api.get("/clinicians", cookies=cookies)
    assert clinicians.status_code == 200
    clinician_id = str(clinicians.json()[0]["id"])
    listed = api.get("/appointment-types", cookies=cookies)
    assert listed.status_code == 200
    types = {str(row["name"]): str(row["id"]) for row in listed.json()}
    return clinician_id, types


def _patient(api: TestClient, cookies: dict[str, str], phone: str) -> str:
    response = api.post(
        "/patients",
        cookies=cookies,
        json={"full_name": "Sample Ada", "phone": phone},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _cookie(api: TestClient, email: str = "clinician@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _other_clinic() -> None:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Other Synthetic Clinic")
        create_user(
            session,
            clinic.id,
            "other@x.test",
            "Other Person",
            PASSWORD,
            ["clinician"],
        )
        session.commit()


def _today() -> date:
    return datetime.now(UTC).astimezone(CLINIC_ZONE).date()
