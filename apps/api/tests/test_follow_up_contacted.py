"""POST /follow-ups/{id}/contacted: scheduled to contacted, no undo, audit, roles."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.app_user import AppUser
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.follow_up import FollowUp
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.audit_service import record as record_audit
from dentacircle.services.follow_up_service import mark_contacted
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api

_ZONE = ZoneInfo("Asia/Kolkata")
_QUEUE_FIELDS = {"id", "status", "due_on", "timing", "patient"}
_MARKER = "contacted-marker-value"


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_scheduled_becomes_contacted_and_the_button_shape_is_the_list_item(
    api: TestClient,
) -> None:
    follow_up_id, patient_id = _scheduled(api)
    cookies = _cookie(api)
    response = api.post(f"/follow-ups/{follow_up_id}/contacted", cookies=cookies)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == _QUEUE_FIELDS
    assert body["id"] == follow_up_id
    assert body["status"] == "contacted"
    assert body["patient"]["id"] == patient_id
    assert body["patient"]["full_name"] == "Sample Ada"
    assert _status_of(follow_up_id) == "contacted"
    listed = api.get("/follow-ups", cookies=cookies)
    assert listed.json()["items"][0]["status"] == "contacted"


def test_contacted_or_booked_is_409_and_writes_nothing(api: TestClient) -> None:
    cookies = _cookie(api)
    for status in ("contacted", "booked"):
        follow_up_id, _patient_id = _scheduled(api, name=f"Sample {status}", phone=_phone(status))
        _set_status(UUID(follow_up_id), status)
        before = _snapshot()
        response = api.post(f"/follow-ups/{follow_up_id}/contacted", cookies=cookies)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_status"
        assert _snapshot() == before
        assert _status_of(follow_up_id) == status


def test_inactive_patient_is_409_and_writes_nothing(api: TestClient) -> None:
    follow_up_id, patient_id = _scheduled(api)
    _set_inactive(UUID(patient_id))
    before = _snapshot()
    response = api.post(f"/follow-ups/{follow_up_id}/contacted", cookies=_cookie(api))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "patient_inactive"
    assert _snapshot() == before
    assert _status_of(follow_up_id) == "scheduled"


def test_checks_run_session_then_role_then_missing(api: TestClient) -> None:
    missing = str(uuid4())
    api.cookies.clear()
    anonymous = api.post(f"/follow-ups/{missing}/contacted")
    assert anonymous.status_code == 401
    denied = api.post(f"/follow-ups/{missing}/contacted", cookies=_cookie(api, "inventory@x.test"))
    assert denied.status_code == 403
    unknown = api.post(f"/follow-ups/{missing}/contacted", cookies=_cookie(api, "clinician@x.test"))
    assert unknown.status_code == 404
    assert missing not in unknown.text
    assert _MARKER not in unknown.text


def test_another_clinic_is_not_found(api: TestClient) -> None:
    other = _other_clinic_follow_up()
    response = api.post(f"/follow-ups/{other}/contacted", cookies=_cookie(api))
    assert response.status_code == 404
    assert other not in response.text
    assert _status_of(other) == "scheduled"


def test_contacted_writes_a_status_change_and_not_the_values(api: TestClient) -> None:
    follow_up_id, _patient_id = _scheduled(api)
    cookies = _cookie(api, "clinician@x.test")
    response = api.post(f"/follow-ups/{follow_up_id}/contacted", cookies=cookies)
    assert response.status_code == 200
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        events = AuditRepository(session, actor.clinic_id).list_for_entity(
            "follow_up", UUID(follow_up_id)
        )
        changed = [event for event in events if event.action == "status_change"]
        assert len(changed) == 1
        assert changed[0].changed_fields == ["status"]
        assert changed[0].actor_user_id == actor.id
        stored = _audit_text(session)
        assert "Sample Ada" not in stored
        assert "scheduled" not in stored
        assert "contacted" not in stored


def test_a_failed_contacted_audit_saves_nothing(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    follow_up_id, _patient_id = _scheduled(api)
    before = _snapshot()

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
            mark_contacted(session, clinic_id, actor_id, UUID(follow_up_id), datetime.now(UTC))
    assert _snapshot() == before
    assert _status_of(follow_up_id) == "scheduled"


def _scheduled(
    api: TestClient, name: str = "Sample Ada", phone: str = "9000000001"
) -> tuple[str, str]:
    patient_id = _patient(api, name, phone)
    due_on = datetime.now(UTC).astimezone(_ZONE).date()
    created = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": due_on.isoformat()},
    )
    assert created.status_code == 201
    return str(created.json()["follow_up"]["id"]), patient_id


def _patient(api: TestClient, name: str, phone: str) -> str:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": name, "phone": phone},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


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
            "other-contact@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, _MARKER, "9000000099", None)
        session.commit()
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


def _audit_text(session: Session) -> str:
    rows = session.execute(text("SELECT * FROM audit_event")).mappings().all()
    return " ".join(str(value) for row in rows for value in row.values())


def _actor() -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        return actor.clinic_id, actor.id


def _phone(status: str) -> str:
    return {"contacted": "9000000002", "booked": "9000000003"}[status]


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}
