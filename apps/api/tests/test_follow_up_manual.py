"""POST /patients/{id}/follow-up creates one open follow-up with no visit."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.follow_up import FOLLOW_UP_CREATE_ROLES
from dentacircle.models.app_user import AppUser
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.follow_up import FollowUp
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.audit_service import record as record_audit
from dentacircle.services.patient_service import register_patient
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
_MARKER = "manual-follow-up-marker"
_FIELDS = {"id", "patient_id", "appointment_id", "status", "due_on", "created_at"}


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def test_create_returns_a_scheduled_follow_up_with_no_visit(api: TestClient) -> None:
    patient_id = _patient(api)
    due_on = _today() + timedelta(days=7)
    before = _audit_count()
    response = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": due_on.isoformat()},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"follow_up"}
    row = body["follow_up"]
    assert set(row) == _FIELDS
    assert row["patient_id"] == patient_id
    assert row["appointment_id"] is None
    assert row["status"] == "scheduled"
    assert row["due_on"] == due_on.isoformat()
    assert "T" not in row["due_on"]
    assert _MARKER not in response.text
    stored_id, stored_due, stored_status, stored_visit = _only(UUID(patient_id))
    assert stored_visit is None
    assert stored_due == due_on
    assert stored_status == "scheduled"
    with Session(get_engine()) as session:
        actor = session.scalars(select(AppUser).where(AppUser.email == "clinician@x.test")).one()
        actor_id = actor.id
        events = AuditRepository(session, actor.clinic_id).list_for_entity("follow_up", stored_id)
        recorded = [
            (event.action, list(event.changed_fields), event.actor_user_id) for event in events
        ]
    assert recorded == [("create", [], actor_id)]
    assert _audit_count() == before + 1


def test_due_on_must_be_today_through_one_year(api: TestClient) -> None:
    patient_id = _patient(api)
    today = _today()
    cookies = _cookie(api, "receptionist@x.test")
    for due_on in (today, today + timedelta(days=365)):
        owner = _patient(api)
        response = api.post(
            f"/patients/{owner}/follow-up",
            cookies=cookies,
            json={"due_on": due_on.isoformat()},
        )
        assert response.status_code == 201
        assert response.json()["follow_up"]["due_on"] == due_on.isoformat()

    before = _snapshot()
    cases = (
        ({"due_on": (today - timedelta(days=1)).isoformat()}, "before_today"),
        ({"due_on": (today + timedelta(days=366)).isoformat()}, "beyond_horizon"),
        ({}, "missing"),
        ({"due_on": "not-a-date"}, "date_from_datetime_parsing"),
        ({"due_on": today.isoformat(), "note": "no"}, "extra_forbidden"),
    )
    for payload, rule in cases:
        response = api.post(
            f"/patients/{patient_id}/follow-up",
            cookies=cookies,
            json=payload,
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        if rule == "extra_forbidden":
            assert "note" in error["message"]
        else:
            assert "due_on" in error["message"]
        if rule not in ("missing", "date_from_datetime_parsing"):
            assert rule in error["message"]
        assert _snapshot() == before


def test_an_open_follow_up_blocks_another_and_a_closed_one_does_not(api: TestClient) -> None:
    patient_id = _patient(api)
    cookies = _cookie(api, "admin@x.test")
    due_on = _today() + timedelta(days=3)
    first = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=cookies,
        json={"due_on": due_on.isoformat()},
    )
    assert first.status_code == 201
    before = _snapshot()
    for status in ("scheduled", "contacted", "booked"):
        _set_status(UUID(first.json()["follow_up"]["id"]), status)
        again = api.post(
            f"/patients/{patient_id}/follow-up",
            cookies=cookies,
            json={"due_on": (_today() + timedelta(days=4)).isoformat()},
        )
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "follow_up_open"
        assert _count() == 1
    kept_id, kept_due, _status, _visit = _only(UUID(patient_id))
    assert kept_due == due_on
    assert _snapshot()[1] == before[1]

    for status in ("completed", "cancelled"):
        _set_status(kept_id, status)
        created = api.post(
            f"/patients/{patient_id}/follow-up",
            cookies=cookies,
            json={"due_on": (_today() + timedelta(days=5)).isoformat()},
        )
        assert created.status_code == 201
        assert created.json()["follow_up"]["appointment_id"] is None
        _set_status(UUID(created.json()["follow_up"]["id"]), "completed")


def test_an_inactive_patient_is_refused(api: TestClient) -> None:
    patient_id = _patient(api)
    cookies = _cookie(api, "clinician@x.test")
    updated = api.put(
        f"/patients/{patient_id}/status",
        cookies=cookies,
        json={"status": "inactive"},
    )
    assert updated.status_code == 200
    before = _snapshot()
    response = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=cookies,
        json={"due_on": _today().isoformat()},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "patient_inactive"
    assert _snapshot() == before


def test_a_failed_audit_saves_no_follow_up(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    patient_id = _patient(api)
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
        if entity_type == "follow_up":
            raise IntegrityError("INSERT", {}, Exception("forced"))
        record_audit(
            session, clinic_id, actor_user_id, entity_type, entity_id, action, changed_fields
        )

    monkeypatch.setattr("dentacircle.services.follow_up_service.record", fail_follow_up)
    response = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": _today().isoformat()},
    )
    assert response.status_code == 500
    assert _snapshot() == before


def test_roles_and_check_order(api: TestClient) -> None:
    missing = str(uuid4())
    bad = {"due_on": "nope"}
    api.cookies.clear()
    anonymous = api.post(f"/patients/{missing}/follow-up", json=bad)
    assert anonymous.status_code == 401

    denied = api.post(
        f"/patients/{missing}/follow-up",
        cookies=_cookie(api, "inventory@x.test"),
        json=bad,
    )
    assert denied.status_code == 403

    unknown = api.post(
        f"/patients/{missing}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json=bad,
    )
    assert unknown.status_code == 404
    assert _MARKER not in unknown.text

    patient_id = _patient(api)
    invalid = api.post(
        f"/patients/{patient_id}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json=bad,
    )
    assert invalid.status_code == 422
    assert "due_on" in invalid.json()["error"]["message"]

    for role in _ROLES:
        owner = _patient(api)
        before = _snapshot()
        response = api.post(
            f"/patients/{owner}/follow-up",
            cookies=_cookie(api, _EMAILS[role]),
            json={"due_on": _today().isoformat()},
        )
        if role in FOLLOW_UP_CREATE_ROLES:
            assert response.status_code == 201
            assert response.json()["follow_up"]["appointment_id"] is None
            assert _count_for(UUID(owner)) == 1
        else:
            assert response.status_code == 403
            assert _snapshot() == before
    api.cookies.clear()
    untouched = _patient(api)
    before = _snapshot()
    # The patient was created with a cookie. Clear it and refuse the follow-up.
    api.cookies.clear()
    refused = api.post(
        f"/patients/{untouched}/follow-up",
        json={"due_on": _today().isoformat()},
    )
    assert refused.status_code == 401
    assert _snapshot() == before


def test_another_clinic_is_not_found(api: TestClient) -> None:
    own = _patient(api)
    other = _other_patient()
    before = _snapshot()
    response = api.post(
        f"/patients/{other}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": _today().isoformat()},
    )
    assert response.status_code == 404
    assert _MARKER not in response.text
    assert _snapshot() == before
    created = api.post(
        f"/patients/{own}/follow-up",
        cookies=_cookie(api, "clinician@x.test"),
        json={"due_on": _today().isoformat()},
    )
    assert created.status_code == 201
    assert _count_for(UUID(own)) == 1


def _today() -> date:
    return datetime.now(UTC).astimezone(_ZONE).date()


def _patient(api: TestClient) -> str:
    response = api.post(
        "/patients",
        cookies=_cookie(api),
        json={"full_name": "Sample Ada", "phone": "9000000001"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _other_patient() -> str:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Other Clinic")
        actor = create_user(
            session,
            clinic.id,
            "b@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, _MARKER, "9000000002", None)
        session.commit()
        return str(patient.id)


def _cookie(api: TestClient, email: str = "receptionist@x.test") -> dict[str, str]:
    return {"dc_session": login(api, email)}


def _set_status(follow_up_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE follow_up SET status = :status WHERE id = :id"),
            {"status": status, "id": follow_up_id},
        )
        session.commit()


def _only(patient_id: UUID) -> tuple[UUID, date, str, UUID | None]:
    with Session(get_engine()) as session:
        row = session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)).one()
        return row.id, row.due_on, row.status, row.appointment_id


def _count() -> int:
    with Session(get_engine()) as session:
        found = session.scalar(select(func.count()).select_from(FollowUp))
    return int(found or 0)


def _count_for(patient_id: UUID) -> int:
    with Session(get_engine()) as session:
        found = session.scalar(
            select(func.count()).select_from(FollowUp).where(FollowUp.patient_id == patient_id)
        )
    return int(found or 0)


def _audit_count() -> int:
    with Session(get_engine()) as session:
        found = session.scalar(select(func.count()).select_from(AuditEvent))
    return int(found or 0)


def _snapshot() -> tuple[list[tuple[str, str | None, str, str]], int]:
    with Session(get_engine()) as session:
        rows = [
            (
                str(row.id),
                None if row.appointment_id is None else str(row.appointment_id),
                row.status,
                row.due_on.isoformat(),
            )
            for row in session.scalars(select(FollowUp).order_by(FollowUp.id))
        ]
        audits = session.scalar(select(func.count()).select_from(AuditEvent))
    return rows, int(audits or 0)
