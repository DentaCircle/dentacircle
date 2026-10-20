"""POST /follow-ups/{id}/book: one transaction, same booking rules, rollback on failure."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.follow_up import FollowUp
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.audit_service import record as record_audit
from dentacircle.services.follow_up_service import book_follow_up
from dentacircle.services.patient_service import set_patient_status
from dentacircle.services.provisioning_service import create_user
from tests.patient_harness import login, patient_api

_ZONE = ZoneInfo("Asia/Kolkata")
_VISIT_FIELDS = {
    "id",
    "patient_id",
    "starts_at",
    "ends_at",
    "status",
    "clinician",
    "appointment_type",
}
_MARKER = "book-marker-value"


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_booking_from_scheduled_sets_booked_and_stores_the_visit(api: TestClient) -> None:
    follow_up_id, patient_id, clinician_id, type_id = _open(api)
    start = _future_at(10, 0)
    response = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=_cookie(api),
        json=_body(clinician_id, type_id, start),
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == _VISIT_FIELDS
    assert body["patient_id"] == patient_id
    assert body["status"] == "scheduled"
    assert body["starts_at"] == start.isoformat()
    assert body["clinician"]["id"] == clinician_id
    row = _follow_up(follow_up_id)
    assert row.status == "booked"
    assert str(row.booked_appointment_id) == body["id"]
    assert _appointment_count() == 1


def test_booking_from_contacted_also_works(api: TestClient) -> None:
    follow_up_id, patient_id, clinician_id, type_id = _open(api, status="contacted")
    start = _future_at(10, 0)
    response = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=_cookie(api),
        json=_body(clinician_id, type_id, start),
    )
    assert response.status_code == 201
    assert response.json()["patient_id"] == patient_id
    assert _follow_up(follow_up_id).status == "booked"


def test_already_booked_is_409_and_creates_no_visit(api: TestClient) -> None:
    follow_up_id, _patient_id, clinician_id, type_id = _open(api, status="booked")
    before = _counts()
    response = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=_cookie(api),
        json=_body(clinician_id, type_id, _future_at(10, 0)),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status"
    assert _counts() == before
    assert _follow_up(follow_up_id).status == "booked"
    assert _follow_up(follow_up_id).booked_appointment_id is None


def test_a_taken_slot_rolls_back_the_follow_up(api: TestClient) -> None:
    follow_up_id, _patient_id, clinician_id, type_id = _open(api)
    other = _patient(api, "Sample Bea", "9000000002")
    start = _future_at(10, 0)
    taken = api.post(
        "/appointments",
        cookies=_cookie(api),
        json={
            "patient_id": other,
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": start.isoformat(),
        },
    )
    assert taken.status_code == 201
    response = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=_cookie(api),
        json=_body(clinician_id, type_id, start),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slot_taken"
    assert start.isoformat() not in response.text
    assert _follow_up(follow_up_id).status == "scheduled"
    assert _follow_up(follow_up_id).booked_appointment_id is None
    assert _appointment_count() == 1


def test_a_busy_patient_rolls_back_the_follow_up(api: TestClient) -> None:
    follow_up_id, patient_id, clinician_id, type_id = _open(api)
    start = _future_at(10, 0)
    other_clinician = _second_clinician()
    existing = api.post(
        "/appointments",
        cookies=_cookie(api),
        json={
            "patient_id": patient_id,
            "clinician_id": other_clinician,
            "appointment_type_id": type_id,
            "starts_at": start.isoformat(),
        },
    )
    assert existing.status_code == 201
    response = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=_cookie(api),
        json=_body(clinician_id, type_id, start),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "patient_busy"
    assert _follow_up(follow_up_id).status == "scheduled"
    assert _appointment_count() == 1


def test_invalid_fields_are_422_and_write_nothing(api: TestClient) -> None:
    follow_up_id, _patient_id, clinician_id, type_id = _open(api)
    cookies = _cookie(api)
    before = _counts()
    naive = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=cookies,
        json={
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": "2026-10-21T10:00:00",
        },
    )
    assert naive.status_code == 422
    extra = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=cookies,
        json={
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": _future_at(10, 0).isoformat(),
            "patient_id": str(uuid4()),
            "notes": _MARKER,
        },
    )
    assert extra.status_code == 422
    assert _MARKER not in extra.text
    unknown = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=cookies,
        json=_body(str(uuid4()), type_id, _future_at(11, 0)),
    )
    assert unknown.status_code == 422
    assert "body.clinician_id" in unknown.json()["error"]["message"]
    assert _counts() == before
    assert _follow_up(follow_up_id).status == "scheduled"


def test_unknown_follow_up_is_404_before_422(api: TestClient) -> None:
    missing = str(uuid4())
    api.cookies.clear()
    anonymous = api.post(f"/follow-ups/{missing}/book", json={})
    assert anonymous.status_code == 401
    denied = api.post(
        f"/follow-ups/{missing}/book",
        cookies=_cookie(api, "inventory@x.test"),
        json={},
    )
    assert denied.status_code == 403
    unknown = api.post(
        f"/follow-ups/{missing}/book",
        cookies=_cookie(api, "clinician@x.test"),
        json={},
    )
    assert unknown.status_code == 404
    assert missing not in unknown.text


def test_inactive_patient_is_409_and_creates_no_visit(api: TestClient) -> None:
    follow_up_id, patient_id, clinician_id, type_id = _open(api)
    _set_inactive(UUID(patient_id))
    before = _counts()
    response = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=_cookie(api),
        json=_body(clinician_id, type_id, _future_at(10, 0)),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "patient_inactive"
    assert _counts() == before
    assert _follow_up(follow_up_id).status == "scheduled"


def test_book_writes_the_visit_create_and_the_follow_up_status_change(
    api: TestClient,
) -> None:
    follow_up_id, _patient_id, clinician_id, type_id = _open(api)
    response = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=_cookie(api, "clinician@x.test"),
        json=_body(clinician_id, type_id, _future_at(10, 0)),
    )
    assert response.status_code == 201
    visit_id = UUID(response.json()["id"])
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        visit_events = AuditRepository(session, actor.clinic_id).list_for_entity(
            "appointment", visit_id
        )
        follow_events = AuditRepository(session, actor.clinic_id).list_for_entity(
            "follow_up", UUID(follow_up_id)
        )
        created = next(event for event in visit_events if event.action == "create")
        changed = next(event for event in follow_events if event.action == "status_change")
        assert created.actor_user_id == actor.id
        assert created.changed_fields == []
        assert changed.actor_user_id == actor.id
        assert changed.changed_fields == ["status", "booked_appointment_id"]
        stored = _audit_text(session)
        assert "Sample Ada" not in stored


def test_a_failed_book_audit_saves_nothing(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    follow_up_id, patient_id, clinician_id, type_id = _open(api)
    before = _counts()

    def fail_follow_up(
        session: Session,
        clinic_id: UUID,
        actor_user_id: UUID,
        entity_type: str,
        entity_id: UUID,
        action: str,
        changed_fields: list[str] | None = None,
    ) -> None:
        if entity_type == "follow_up" and action == "status_change":
            raise IntegrityError("INSERT", {}, Exception("forced"))
        record_audit(
            session, clinic_id, actor_user_id, entity_type, entity_id, action, changed_fields
        )

    monkeypatch.setattr("dentacircle.services.follow_up_service.record", fail_follow_up)
    clinic_id, actor_id = _actor()
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            book_follow_up(
                session,
                clinic_id,
                actor_id,
                UUID(follow_up_id),
                UUID(clinician_id),
                UUID(type_id),
                _future_at(10, 0),
                datetime.now(UTC),
            )
    assert _counts() == before
    assert _follow_up(follow_up_id).status == "scheduled"
    assert _follow_up(follow_up_id).booked_appointment_id is None
    assert _appointment_count() == 0
    assert patient_id


def _open(api: TestClient, status: str = "scheduled") -> tuple[str, str, str, str]:
    patient_id = _patient(api, "Sample Ada", "9000000001")
    due_on = datetime.now(UTC).astimezone(_ZONE).date()
    created = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": due_on.isoformat()},
    )
    assert created.status_code == 201
    follow_up_id = str(created.json()["follow_up"]["id"])
    if status != "scheduled":
        _set_status(UUID(follow_up_id), status)
    clinician_id, type_id = _clinician_and_type()
    return follow_up_id, patient_id, clinician_id, type_id


def _patient(api: TestClient, name: str, phone: str) -> str:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": name, "phone": phone},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _clinician_and_type() -> tuple[str, str]:
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
        return str(clinician.id), str(consultation.id)


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


def _set_status(follow_up_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE follow_up SET status = :status WHERE id = :id"),
            {"status": status, "id": follow_up_id},
        )
        session.commit()


def _set_inactive(patient_id: UUID) -> None:
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        set_patient_status(session, actor.clinic_id, actor.id, patient_id, "inactive")
        session.commit()


class _FollowUpRow:
    def __init__(self, status: str, booked_appointment_id: UUID | None) -> None:
        self.status = status
        self.booked_appointment_id = booked_appointment_id


def _follow_up(follow_up_id: str) -> _FollowUpRow:
    with Session(get_engine()) as session:
        row = session.get(FollowUp, UUID(follow_up_id))
        assert row is not None
        return _FollowUpRow(row.status, row.booked_appointment_id)


def _counts() -> tuple[list[tuple[str, str, str | None]], int, int]:
    with Session(get_engine()) as session:
        rows = [
            (
                str(row.id),
                row.status,
                None if row.booked_appointment_id is None else str(row.booked_appointment_id),
            )
            for row in session.scalars(select(FollowUp).order_by(FollowUp.id))
        ]
        visits = int(session.scalar(select(func.count()).select_from(Appointment)) or 0)
        audits = int(session.scalar(select(func.count()).select_from(AuditEvent)) or 0)
    return rows, visits, audits


def _appointment_count() -> int:
    with Session(get_engine()) as session:
        return int(session.scalar(select(func.count()).select_from(Appointment)) or 0)


def _audit_text(session: Session) -> str:
    rows = session.execute(text("SELECT * FROM audit_event")).mappings().all()
    return " ".join(str(value) for row in rows for value in row.values())


def _actor() -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        return actor.clinic_id, actor.id


def _body(clinician_id: str, type_id: str, starts_at: datetime) -> dict[str, str]:
    return {
        "clinician_id": clinician_id,
        "appointment_type_id": type_id,
        "starts_at": starts_at.isoformat(),
    }


def _future_at(hour: int, minute: int, days: int = 1) -> datetime:
    now = datetime.now(_ZONE)
    day = now.date() + timedelta(days=days)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=_ZONE)


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}
