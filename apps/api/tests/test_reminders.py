"""Reminder scheduling, transitions, and visit hooks."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.app_user import AppUser
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.reminder import Reminder
from dentacircle.services.reminder_service import ReminderConflictError, resolve, schedule
from tests.patient_harness import patient_api
from tests.test_appointment_routes import _book, _cookie, _future_at, _ids


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


def _visit(api: TestClient) -> tuple[str, datetime]:
    patient, clinician, kind = _ids(api)
    start = _future_at(10, 0)
    response = _book(api, patient, clinician, kind, start)
    assert response.status_code == 201
    return response.json()["id"], start


def _identity() -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        user = session.scalars(select(AppUser).where(AppUser.email == "receptionist@x.test")).one()
        return user.clinic_id, user.id


def test_api_schedule_queue_and_final_transitions(api: TestClient) -> None:
    visit, start = _visit(api)
    cookie = _cookie(api)
    path = f"/appointments/{visit}/reminders"
    assert api.post(path, cookies=cookie, json={"due_at": "2030-01-01T10:00:00"}).status_code == 422
    assert (
        api.post(
            path,
            cookies=cookie,
            json={"due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        ).status_code
        == 422
    )
    assert api.post(path, cookies=cookie, json={"due_at": start.isoformat()}).status_code == 422
    future = datetime.now(UTC) + timedelta(minutes=5)
    first = api.post(path, cookies=cookie, json={"due_at": future.isoformat()})
    assert first.status_code == 201
    reminder = first.json()["id"]
    assert api.post(path, cookies=cookie, json={}).status_code == 409
    assert api.get("/reminders?view=due", cookies=cookie).json()["total"] == 0
    listed = api.get("/reminders?view=pending", cookies=cookie).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == reminder
    assert api.post(f"/reminders/{reminder}/complete", cookies=cookie).status_code == 204
    assert api.post(f"/reminders/{reminder}/cancel", cookies=cookie).status_code == 409
    again = api.post(path, cookies=cookie, json={})
    assert again.status_code == 201
    assert api.get("/reminders", cookies=cookie).json()["total"] == 1
    assert api.post(f"/reminders/{again.json()['id']}/cancel", cookies=cookie).status_code == 204
    with Session(get_engine()) as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.entity_type == "reminder")
        ).all()
        assert sorted(event.action for event in events) == [
            "create",
            "create",
            "status_change",
            "status_change",
        ]


def test_access_and_cross_clinic_ids(api: TestClient) -> None:
    visit, _ = _visit(api)
    path = f"/appointments/{visit}/reminders"
    api.cookies.clear()
    assert api.get("/reminders").status_code == 401
    inventory = _cookie(api, "inventory@x.test")
    assert api.get("/reminders", cookies=inventory).status_code == 403
    assert api.post(path, cookies=inventory, json={}).status_code == 403
    assert api.post(f"/reminders/{uuid4()}/cancel", cookies=_cookie(api)).status_code == 404
    for role in ("receptionist", "clinician", "admin"):
        email = f"{role}@x.test"
        assert api.get("/reminders", cookies=_cookie(api, email)).status_code == 200


def test_visit_cancel_cancels_reminder_and_rollback_preserves_it(api: TestClient) -> None:
    visit, _ = _visit(api)
    cookie = _cookie(api)
    reminder = api.post(f"/appointments/{visit}/reminders", cookies=cookie, json={}).json()["id"]
    assert (
        api.post(
            f"/appointments/{visit}/reschedule", cookies=cookie, json={"starts_at": "bad"}
        ).status_code
        == 422
    )
    assert api.get("/reminders", cookies=cookie).json()["total"] == 1
    assert api.post(f"/appointments/{visit}/cancel", cookies=cookie).status_code == 200
    assert api.get("/reminders?view=pending", cookies=cookie).json()["total"] == 0
    assert api.post(f"/reminders/{reminder}/complete", cookies=cookie).status_code == 409
    with Session(get_engine()) as session:
        row = session.get(Reminder, UUID(reminder))
        assert row is not None and row.status == "cancelled" and row.resolved_at is not None


def test_competing_creation_and_transitions_serialize(api: TestClient) -> None:
    visit, _ = _visit(api)
    clinic, actor = _identity()
    now = datetime.now(UTC)

    def create() -> UUID | None:
        with Session(get_engine()) as session:
            try:
                row = schedule(session, clinic, actor, UUID(visit), None, now)
                result = row.id
                session.commit()
                return result
            except ReminderConflictError:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    ids = [result for result in results if result is not None]
    assert len(ids) == 1

    def transition(target: str) -> bool:
        with Session(get_engine()) as session:
            try:
                resolve(session, clinic, actor, ids[0], target, now)
                session.commit()
                return True
            except ReminderConflictError:
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(transition, ["completed", "cancelled"])) == [False, True]


def test_inactive_patient_hidden_and_cancellation_allowed(api: TestClient) -> None:
    visit, _ = _visit(api)
    cookie = _cookie(api)
    reminder = api.post(f"/appointments/{visit}/reminders", cookies=cookie, json={}).json()["id"]
    from dentacircle.models.appointment import Appointment
    from dentacircle.models.patient import Patient

    with Session(get_engine()) as session:
        appointment = session.get(Appointment, UUID(visit))
        assert appointment is not None
        patient = session.get(Patient, appointment.patient_id)
        assert patient is not None
        patient.status = "inactive"
        session.commit()
    assert api.get("/reminders?view=pending", cookies=cookie).json()["total"] == 0
    assert api.post(f"/reminders/{reminder}/complete", cookies=cookie).status_code == 409
    assert api.post(f"/reminders/{reminder}/cancel", cookies=cookie).status_code == 204
    assert api.post(f"/appointments/{visit}/reminders", cookies=cookie, json={}).status_code == 409


def test_reschedule_cancels_only_when_time_changes(api: TestClient) -> None:
    from tests.test_appointment_routes import _second_clinician

    visit, start = _visit(api)
    cookie = _cookie(api)
    reminder = api.post(f"/appointments/{visit}/reminders", cookies=cookie, json={}).json()["id"]
    clinician = _second_clinician()
    moved = api.post(
        f"/appointments/{visit}/reschedule",
        cookies=cookie,
        json={"starts_at": start.isoformat(), "clinician_id": clinician},
    )
    assert moved.status_code == 200
    assert api.get("/reminders", cookies=cookie).json()["total"] == 1
    moved = api.post(
        f"/appointments/{visit}/reschedule",
        cookies=cookie,
        json={"starts_at": (start + timedelta(hours=1)).isoformat(), "clinician_id": clinician},
    )
    assert moved.status_code == 200
    assert api.get("/reminders?view=pending", cookies=cookie).json()["total"] == 0
    assert api.post(f"/reminders/{reminder}/cancel", cookies=cookie).status_code == 409
    assert api.post(f"/appointments/{visit}/reminders", cookies=cookie, json={}).status_code == 201


def test_service_rollback_restores_visit_and_reminder(api: TestClient) -> None:
    from dentacircle.services.appointment_service import cancel_appointment

    visit, _ = _visit(api)
    clinic, actor = _identity()
    now = datetime.now(UTC)
    with Session(get_engine()) as session:
        reminder = schedule(session, clinic, actor, UUID(visit), None, now)
        reminder_id = reminder.id
        session.commit()
    with Session(get_engine()) as session:
        cancel_appointment(session, clinic, actor, UUID(visit), now)
        session.rollback()
    with Session(get_engine()) as session:
        row = session.get(Reminder, reminder_id)
        assert row is not None and row.status == "pending" and row.resolved_at is None


def test_other_clinic_cannot_read_or_change_reminder(api: TestClient) -> None:
    from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
    from tests.patient_harness import PASSWORD

    visit, _ = _visit(api)
    cookie = _cookie(api)
    reminder = api.post(f"/appointments/{visit}/reminders", cookies=cookie, json={}).json()["id"]
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Other Synthetic Clinic")
        create_user(session, clinic.id, "other@x.test", "Sample Staff", PASSWORD, ["receptionist"])
        session.commit()
    other = _cookie(api, "other@x.test")
    assert api.get("/reminders?view=pending", cookies=other).json()["total"] == 0
    assert api.post(f"/reminders/{reminder}/cancel", cookies=other).status_code == 404
    assert api.post(f"/appointments/{visit}/reminders", cookies=other, json={}).status_code == 404


@pytest.mark.parametrize("target", ["arrived", "no_show"])
def test_status_changes_cancel_pending_reminders(api: TestClient, target: str) -> None:
    from dentacircle.services.appointment_service import change_status

    visit, start = _visit(api)
    clinic, actor = _identity()
    now = start - timedelta(minutes=30)
    with Session(get_engine()) as session:
        reminder = schedule(session, clinic, actor, UUID(visit), None, now)
        reminder_id = reminder.id
        session.commit()
    with Session(get_engine()) as session:
        change_status(
            session,
            clinic,
            actor,
            ["receptionist"],
            UUID(visit),
            target,
            start if target == "no_show" else now,
        )
        session.commit()
    with Session(get_engine()) as session:
        row = session.get(Reminder, reminder_id)
        assert row is not None and row.status == "cancelled"
        audit = session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_type == "reminder",
                AuditEvent.entity_id == reminder_id,
                AuditEvent.action == "status_change",
            )
        ).one()
        assert audit.actor_user_id == actor


def test_due_order_pagination_and_started_visit_filter(api: TestClient) -> None:
    from dentacircle.models.appointment import Appointment
    from dentacircle.repositories.reminder_repository import ReminderRepository

    visit, start = _visit(api)
    clinic, actor = _identity()
    now = datetime.now(UTC)
    with Session(get_engine()) as session:
        reminder = schedule(session, clinic, actor, UUID(visit), None, now)
        session.commit()
        assert ReminderRepository(session, clinic).list(now, True, 1)[1] == 1
        row = session.get(Appointment, UUID(visit))
        assert row is not None
        row.starts_at = now - timedelta(minutes=10)
        row.ends_at = now + timedelta(minutes=20)
        session.flush()
        assert ReminderRepository(session, clinic).list(now, False, 1)[1] == 0
        session.rollback()
        assert reminder.id is not None
