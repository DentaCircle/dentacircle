"""One patient walks the core loop. The timeline route returns that order, newest first."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from tests.patient_harness import login, patient_api

_ZONE = ZoneInfo("Asia/Kolkata")
_EXPECTED = [
    "follow_up_created",
    "follow_up_completed",
    "visit_completed",
    "visit_started",
    "visit_arrived",
    "follow_up_booked",
    "visit_booked",
    "follow_up_contacted",
    "follow_up_created",
    "visit_completed",
    "care_session_recorded",
    "care_item_completed",
    "visit_started",
    "visit_arrived",
    "visit_booked",
    "care_item_added",
    "care_item_added",
    "patient_registered",
]


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_the_core_loop_is_the_timeline(api: TestClient) -> None:
    cookies = _cookie(api)
    patient_id = _patient(api, cookies)
    done_id, _left_id = _items(api, cookies, patient_id)
    clinician_id, type_id = _ids()
    first = _book(api, cookies, patient_id, clinician_id, type_id, 0)
    _place_today(first, 10)
    _status(api, cookies, first, "arrived")
    _status(api, cookies, first, "in_progress")
    recorded = api.post(
        f"/appointments/{first}/care-session",
        cookies=cookies,
        json={"items": [{"care_item_id": done_id, "status": "completed"}]},
    )
    assert recorded.status_code == 201
    _status(api, cookies, first, "completed")
    follow_up = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
    assert follow_up.status_code == 200
    follow_up_id = follow_up.json()["follow_up"]["id"]
    contacted = api.post(f"/follow-ups/{follow_up_id}/contacted", cookies=cookies)
    assert contacted.status_code == 200
    second = _book_follow_up(api, cookies, follow_up_id, clinician_id, type_id)
    _place_today(second, 11)
    _status(api, cookies, second, "arrived")
    _status(api, cookies, second, "in_progress")
    _status(api, cookies, second, "completed")

    timeline = api.get(
        f"/patients/{patient_id}/timeline",
        cookies=cookies,
        params={"page_size": 100},
    )
    assert timeline.status_code == 200
    assert [item["kind"] for item in timeline.json()["items"]] == _EXPECTED


def _book(
    api: TestClient,
    cookies: dict[str, str],
    patient_id: str,
    clinician_id: str,
    type_id: str,
    slot_index: int,
) -> str:
    start = _slot(api, cookies, clinician_id, type_id, slot_index)
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


def _book_follow_up(
    api: TestClient,
    cookies: dict[str, str],
    follow_up_id: str,
    clinician_id: str,
    type_id: str,
) -> str:
    start = _slot(api, cookies, clinician_id, type_id, 0)
    response = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=cookies,
        json={
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": start,
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _slot(
    api: TestClient,
    cookies: dict[str, str],
    clinician_id: str,
    type_id: str,
    slot_index: int,
) -> str:
    today = datetime.now(UTC).astimezone(_ZONE).date()
    for offset in range(8):
        day = today + timedelta(days=offset)
        if day.weekday() == 6:
            continue
        found = api.get(
            "/appointments/availability",
            cookies=cookies,
            params={
                "date": day.isoformat(),
                "clinician_id": clinician_id,
                "appointment_type_id": type_id,
            },
        )
        assert found.status_code == 200
        slots = found.json()["slots"]
        if len(slots) > slot_index:
            return str(slots[slot_index]["starts_at"])
    raise AssertionError("no open slot")


def _place_today(visit_id: str, hour: int) -> None:
    """Arrived is only allowed on the visit's clinic-local day. A slot after hours is moved."""
    today = datetime.now(UTC).astimezone(_ZONE).date()
    start = datetime(today.year, today.month, today.day, hour, 0, tzinfo=_ZONE)
    end = start + timedelta(minutes=30)
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE appointment SET starts_at = :start, ends_at = :end WHERE id = :id"),
            {"start": start, "end": end, "id": UUID(visit_id)},
        )
        session.commit()


def _status(api: TestClient, cookies: dict[str, str], visit_id: str, status: str) -> None:
    response = api.post(
        f"/appointments/{visit_id}/status",
        cookies=cookies,
        json={"status": status},
    )
    assert response.status_code == 200
    assert response.json()["status"] == status


def _items(api: TestClient, cookies: dict[str, str], patient_id: str) -> tuple[str, str]:
    plan = api.post(
        f"/patients/{patient_id}/care-plans",
        cookies=cookies,
        json={"title": "Sample plan"},
    )
    assert plan.status_code == 201
    plan_id = plan.json()["id"]
    done = api.post(f"/care-plans/{plan_id}/items", cookies=cookies, json={"name": "Scaling"})
    left = api.post(f"/care-plans/{plan_id}/items", cookies=cookies, json={"name": "Root canal"})
    assert done.status_code == 201
    assert left.status_code == 201
    return str(done.json()["id"]), str(left.json()["id"])


def _ids() -> tuple[str, str]:
    from sqlalchemy import select

    from dentacircle.models.app_user import AppUser
    from dentacircle.models.appointment_type import AppointmentType

    with Session(get_engine()) as session:
        clinician = session.scalars(
            select(AppUser).where(AppUser.email == "clinician@x.test")
        ).one()
        consultation = session.scalars(
            select(AppointmentType).where(
                AppointmentType.clinic_id == clinician.clinic_id,
                AppointmentType.name == "Consultation",
            )
        ).one()
        return str(clinician.id), str(consultation.id)


def _patient(api: TestClient, cookies: dict[str, str]) -> str:
    response = api.post(
        "/patients",
        cookies=cookies,
        json={"full_name": "Sample Ada", "phone": "9000000001"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _cookie(api: TestClient) -> dict[str, str]:
    return {"dc_session": login(api, "clinician@x.test")}
