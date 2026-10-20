"""Contacted, book and cancel on a recall."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.recall import Recall
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.patient_service import set_patient_status
from tests.patient_harness import login, patient_api

_ZONE = ZoneInfo("Asia/Kolkata")
_MARKER = "recall-action-marker"


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    _SLOT["n"] = 0
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


_SLOT = {"n": 0}


def test_scheduled_becomes_contacted_and_booked_and_cancelled(api: TestClient) -> None:
    recall_id, _visit_id = _recall(api)
    cookies = _cookie(api, "clinician@x.test")
    contacted = api.post(f"/recalls/{recall_id}/contacted", cookies=cookies)
    assert contacted.status_code == 200
    assert contacted.json()["status"] == "contacted"
    assert set(contacted.json()) >= {"id", "status", "due_on", "timing", "patient", "recall_type"}

    booked = api.post(f"/recalls/{recall_id}/book", cookies=cookies, json=_book_body(api))
    assert booked.status_code == 201
    visit_id = booked.json()["id"]
    assert booked.json()["status"] == "scheduled"
    assert _status_of(recall_id) == "booked"
    assert _booked_visit(recall_id) == visit_id

    cancelled = api.post(f"/recalls/{recall_id}/cancel", cookies=cookies)
    assert cancelled.status_code == 204
    assert cancelled.content == b""
    assert _status_of(recall_id) == "cancelled"
    assert _visit_status(visit_id) == "scheduled"


def test_the_wrong_status_and_an_inactive_patient_are_409(api: TestClient) -> None:
    cookies = _cookie(api)
    recall_id, _visit_id = _recall(api, name="Sample Bea", phone="9000000002")
    _set_status(UUID(recall_id), "booked")
    contacted = api.post(f"/recalls/{recall_id}/contacted", cookies=cookies)
    assert contacted.status_code == 409
    assert contacted.json()["error"]["code"] == "invalid_status"
    booked = api.post(f"/recalls/{recall_id}/book", cookies=cookies, json=_book_body(api))
    assert booked.status_code == 409
    assert booked.json()["error"]["code"] == "invalid_status"

    open_id, _open_visit = _recall(api, name="Sample Cyd", phone="9000000003")
    _set_inactive(_patient_of(open_id))
    for path, body in (
        (f"/recalls/{open_id}/contacted", None),
        (f"/recalls/{open_id}/book", _book_body(api)),
        (f"/recalls/{open_id}/cancel", None),
    ):
        response = api.post(path, cookies=cookies, json=body)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "patient_inactive"
    assert _status_of(open_id) == "scheduled"


def test_cancel_works_from_scheduled_and_contacted(api: TestClient) -> None:
    cookies = _cookie(api)
    scheduled_id, _scheduled_visit = _recall(api, name="Sample Ada", phone="9000000001")
    contacted_id, _contacted_visit = _recall(
        api, name="Sample Bea", phone="9000000002", status="contacted"
    )
    assert api.post(f"/recalls/{scheduled_id}/cancel", cookies=cookies).status_code == 204
    assert api.post(f"/recalls/{contacted_id}/cancel", cookies=cookies).status_code == 204
    assert _status_of(scheduled_id) == "cancelled"
    assert _status_of(contacted_id) == "cancelled"


def test_actions_are_audited_without_values(api: TestClient) -> None:
    recall_id, _visit_id = _recall(api)
    cookies = _cookie(api, "clinician@x.test")
    assert api.post(f"/recalls/{recall_id}/contacted", cookies=cookies).status_code == 200
    booked = api.post(f"/recalls/{recall_id}/book", cookies=cookies, json=_book_body(api))
    assert booked.status_code == 201
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        events = AuditRepository(session, actor.clinic_id).list_for_entity(
            "recall", UUID(recall_id)
        )
        changes = [(event.action, event.changed_fields) for event in events]
        assert ("status_change", ["status"]) in changes
        assert ("status_change", ["status", "booked_appointment_id"]) in changes
        assert events[-1].actor_user_id == actor.id
        stored = " ".join(event.action for event in events)
        assert "Sample Ada" not in stored
        assert "contacted" not in stored


def test_checks_run_session_then_role_then_body_then_missing(api: TestClient) -> None:
    missing = str(uuid4())
    api.cookies.clear()
    assert api.post(f"/recalls/{missing}/book", json={"starts_at": "nope"}).status_code == 401
    denied = api.post(
        f"/recalls/{missing}/book",
        cookies=_cookie(api, "inventory@x.test"),
        json={"starts_at": "nope"},
    )
    assert denied.status_code == 403
    bad = api.post(
        f"/recalls/{missing}/book",
        cookies=_cookie(api, "clinician@x.test"),
        json={"starts_at": "nope"},
    )
    assert bad.status_code == 422
    missing_body = {
        "clinician_id": str(uuid4()),
        "appointment_type_id": str(uuid4()),
        "starts_at": datetime.now(UTC).isoformat(),
    }
    unknown = api.post(
        f"/recalls/{missing}/book",
        cookies=_cookie(api, "clinician@x.test"),
        json=missing_body,
    )
    assert unknown.status_code == 404
    contacted = api.post(f"/recalls/{missing}/contacted", cookies=_cookie(api, "clinician@x.test"))
    assert contacted.status_code == 404
    assert missing not in contacted.text
    assert _MARKER not in contacted.text


def test_another_clinic_is_not_found(api: TestClient) -> None:
    other = _other_recall()
    response = api.post(f"/recalls/{other}/cancel", cookies=_cookie(api))
    assert response.status_code == 404
    assert _status_of(other) == "scheduled"


def _recall(
    api: TestClient,
    name: str = "Sample Ada",
    phone: str = "9000000001",
    status: str = "scheduled",
) -> tuple[str, str]:
    patient = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": name, "phone": phone},
    )
    assert patient.status_code == 201
    patient_id = patient.json()["id"]
    visit_id, type_id = _book_source(api, patient_id)
    recall_id = str(uuid4())
    due_on = datetime.now(UTC).astimezone(_ZONE).date()
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
    return recall_id, visit_id


def _book_source(api: TestClient, patient_id: str) -> tuple[str, str]:
    cookies = _cookie(api, "receptionist@x.test")
    types = api.get("/appointment-types", cookies=cookies).json()
    scaling = next(row for row in types if row["name"] == "Scaling")
    clinician_id = api.get("/clinicians", cookies=cookies).json()[0]["id"]
    created = api.post(
        "/appointments",
        cookies=cookies,
        json={
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "appointment_type_id": scaling["id"],
            "starts_at": _next_start().isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"], scaling["id"]


def _book_body(api: TestClient) -> dict[str, str]:
    cookies = _cookie(api, "clinician@x.test")
    types = api.get("/appointment-types", cookies=cookies).json()
    consultation = next(row for row in types if row["name"] == "Consultation")
    clinician_id = api.get("/clinicians", cookies=cookies).json()[0]["id"]
    return {
        "clinician_id": clinician_id,
        "appointment_type_id": consultation["id"],
        "starts_at": _next_start().isoformat(),
    }


def _next_start() -> datetime:
    index = _SLOT["n"]
    _SLOT["n"] += 1
    day = datetime.now(UTC).astimezone(_ZONE).date() + timedelta(days=1 + index // 4)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, 10 + (index % 4) * 2, 0, tzinfo=_ZONE)


def _other_recall() -> str:
    from dentacircle.services.appointment_service import book_appointment
    from dentacircle.services.appointment_type_service import list_appointment_types
    from dentacircle.services.patient_service import register_patient
    from dentacircle.services.provisioning_service import create_user, get_or_create_clinic

    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Other Clinic")
        actor = create_user(
            session, clinic.id, "other-action@x.test", "Other Person", "hash", ["clinician"]
        )
        patient = register_patient(session, clinic.id, actor.id, _MARKER, "9000000099", None)
        session.commit()
        clinic_id = clinic.id
        actor_id = actor.id
        patient_id = patient.id
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
    due_on = datetime.now(UTC).astimezone(_ZONE).date()
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


def _set_status(recall_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(Recall, recall_id)
        assert row is not None
        row.status = status
        session.commit()


def _set_inactive(patient_id: UUID) -> None:
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        set_patient_status(session, actor.clinic_id, actor.id, patient_id, "inactive")
        session.commit()


def _patient_of(recall_id: str) -> UUID:
    with Session(get_engine()) as session:
        row = session.get(Recall, UUID(recall_id))
        assert row is not None
        return row.patient_id


def _status_of(recall_id: str) -> str:
    with Session(get_engine()) as session:
        row = session.get(Recall, UUID(recall_id))
        assert row is not None
        return row.status


def _booked_visit(recall_id: str) -> str:
    with Session(get_engine()) as session:
        row = session.get(Recall, UUID(recall_id))
        assert row is not None
        assert row.booked_appointment_id is not None
        return str(row.booked_appointment_id)


def _visit_status(visit_id: str) -> str:
    with Session(get_engine()) as session:
        row = session.get(Appointment, UUID(visit_id))
        assert row is not None
        return row.status


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}
