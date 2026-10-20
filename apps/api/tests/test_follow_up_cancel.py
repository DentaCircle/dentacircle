"""POST /follow-ups/{id}/cancel: open rows become cancelled, with no undo."""

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
from dentacircle.services.follow_up_service import cancel_follow_up
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api

_ZONE = ZoneInfo("Asia/Kolkata")
_MARKER = "cancel-marker-value"
_PHONE = {"n": 1}


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    _PHONE["n"] = 1
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_each_open_status_cancels_and_returns_204(api: TestClient) -> None:
    cookies = _cookie(api, "clinician@x.test")
    for status in ("scheduled", "contacted", "booked"):
        follow_up_id, _patient_id = _scheduled(api)
        if status != "scheduled":
            _set_status(UUID(follow_up_id), status)
        response = api.post(f"/follow-ups/{follow_up_id}/cancel", cookies=cookies)
        assert response.status_code == 204
        assert response.content == b""
        assert _status_of(follow_up_id) == "cancelled"


def test_a_closed_row_is_409_and_writes_nothing(api: TestClient) -> None:
    cookies = _cookie(api)
    for status in ("completed", "cancelled"):
        follow_up_id, _patient_id = _scheduled(api)
        _set_status(UUID(follow_up_id), status)
        before = _snapshot()
        response = api.post(f"/follow-ups/{follow_up_id}/cancel", cookies=cookies)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_status"
        assert _snapshot() == before
        assert _status_of(follow_up_id) == status


def test_an_inactive_patient_is_409_and_writes_nothing(api: TestClient) -> None:
    follow_up_id, patient_id = _scheduled(api)
    _set_inactive(UUID(patient_id))
    before = _snapshot()
    response = api.post(f"/follow-ups/{follow_up_id}/cancel", cookies=_cookie(api))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "patient_inactive"
    assert _snapshot() == before
    assert _status_of(follow_up_id) == "scheduled"


def test_checks_run_session_then_role_then_missing(api: TestClient) -> None:
    missing = str(uuid4())
    api.cookies.clear()
    anonymous = api.post(f"/follow-ups/{missing}/cancel")
    assert anonymous.status_code == 401
    denied = api.post(f"/follow-ups/{missing}/cancel", cookies=_cookie(api, "inventory@x.test"))
    assert denied.status_code == 403
    unknown = api.post(f"/follow-ups/{missing}/cancel", cookies=_cookie(api, "clinician@x.test"))
    assert unknown.status_code == 404
    assert missing not in unknown.text
    assert _MARKER not in unknown.text


def test_another_clinic_is_not_found(api: TestClient) -> None:
    other = _other_clinic_follow_up()
    response = api.post(f"/follow-ups/{other}/cancel", cookies=_cookie(api))
    assert response.status_code == 404
    assert other not in response.text
    assert _status_of(other) == "scheduled"


def test_allowed_roles_can_cancel(api: TestClient) -> None:
    for email in ("receptionist@x.test", "clinician@x.test", "admin@x.test"):
        follow_up_id, _patient_id = _scheduled(api)
        response = api.post(f"/follow-ups/{follow_up_id}/cancel", cookies=_cookie(api, email))
        assert response.status_code == 204
        assert _status_of(follow_up_id) == "cancelled"


def test_cancelling_a_booked_row_leaves_the_visit(api: TestClient) -> None:
    follow_up_id, visit_id = _booked(api)
    response = api.post(f"/follow-ups/{follow_up_id}/cancel", cookies=_cookie(api))
    assert response.status_code == 204
    assert _status_of(follow_up_id) == "cancelled"
    with Session(get_engine()) as session:
        visit = session.get(Appointment, UUID(visit_id))
    assert visit is not None
    assert visit.status == "scheduled"


def test_a_new_follow_up_can_be_created_afterwards(api: TestClient) -> None:
    follow_up_id, patient_id = _scheduled(api)
    cancelled = api.post(f"/follow-ups/{follow_up_id}/cancel", cookies=_cookie(api))
    assert cancelled.status_code == 204
    due_on = datetime.now(UTC).astimezone(_ZONE).date() + timedelta(days=1)
    created = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": due_on.isoformat()},
    )
    assert created.status_code == 201
    assert created.json()["follow_up"]["status"] == "scheduled"
    assert created.json()["follow_up"]["patient_id"] == patient_id


def test_cancel_writes_a_status_change_and_not_the_values(api: TestClient) -> None:
    follow_up_id, _patient_id = _scheduled(api)
    response = api.post(
        f"/follow-ups/{follow_up_id}/cancel", cookies=_cookie(api, "clinician@x.test")
    )
    assert response.status_code == 204
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        events = AuditRepository(session, actor.clinic_id).list_for_entity(
            "follow_up", UUID(follow_up_id)
        )
        changed = [event for event in events if event.action == "status_change"]
        assert len(changed) == 1
        assert changed[0].changed_fields == ["status"]
        assert changed[0].actor_user_id == actor.id
        stored = " ".join(
            str(value)
            for row in session.execute(text("SELECT * FROM audit_event")).mappings()
            for value in row.values()
        )
    assert "Sample Ada" not in stored
    assert "scheduled" not in stored
    assert "cancelled" not in stored


def test_a_failed_cancel_audit_saves_nothing(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    follow_up_id, _patient_id = _scheduled(api)
    before = _snapshot()
    monkeypatch.setattr("dentacircle.services.follow_up_service.record", _fail_status_change)
    clinic_id, actor_id = _actor()
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            cancel_follow_up(session, clinic_id, actor_id, UUID(follow_up_id))
    assert _snapshot() == before
    assert _status_of(follow_up_id) == "scheduled"


def _fail_status_change(
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
    record_audit(session, clinic_id, actor_user_id, entity_type, entity_id, action, changed_fields)


def _scheduled(api: TestClient) -> tuple[str, str]:
    phone = f"900000{_PHONE['n']:04d}"
    _PHONE["n"] += 1
    patient = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": "Sample Ada", "phone": phone},
    )
    assert patient.status_code == 201
    patient_id = str(patient.json()["id"])
    due_on = datetime.now(UTC).astimezone(_ZONE).date()
    created = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": due_on.isoformat()},
    )
    assert created.status_code == 201
    return str(created.json()["follow_up"]["id"]), patient_id


def _booked(api: TestClient) -> tuple[str, str]:
    follow_up_id, _patient_id = _scheduled(api)
    clinician_id, type_id = _clinician_and_type()
    start = _future_at(10, 0)
    response = api.post(
        f"/follow-ups/{follow_up_id}/book",
        cookies=_cookie(api),
        json={
            "clinician_id": clinician_id,
            "appointment_type_id": type_id,
            "starts_at": start.isoformat(),
        },
    )
    assert response.status_code == 201
    return follow_up_id, str(response.json()["id"])


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


def _future_at(hour: int, minute: int) -> datetime:
    day = datetime.now(_ZONE).date() + timedelta(days=1)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=_ZONE)


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


def _other_clinic_follow_up() -> str:
    due_on = datetime.now(UTC).astimezone(_ZONE).date()
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Other Clinic")
        actor = create_user(
            session,
            clinic.id,
            "other-cancel@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, _MARKER, "9000000099", None)
        from dentacircle.services.follow_up_service import create_manual_follow_up

        created = create_manual_follow_up(
            session, clinic.id, actor.id, patient.id, due_on, datetime.now(UTC)
        )
        session.commit()
    return str(created.id)


def _status_of(follow_up_id: str) -> str:
    with Session(get_engine()) as session:
        row = session.get(FollowUp, UUID(follow_up_id))
    assert row is not None
    return row.status


def _snapshot() -> tuple[list[tuple[str, str]], int]:
    with Session(get_engine()) as session:
        rows = [
            (str(row.id), row.status)
            for row in session.scalars(select(FollowUp).order_by(FollowUp.id))
        ]
        audits = session.scalar(select(func.count()).select_from(AuditEvent))
    return rows, int(audits or 0)


def _actor() -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        return actor.clinic_id, actor.id


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}
