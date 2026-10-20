"""A clinician date on completion creates or moves the one open follow-up."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from datetime import tzinfo as TzInfo
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.appointment import STATUS_TARGETS
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.follow_up import FollowUp
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.repositories.follow_up_repository import FollowUpRepository
from dentacircle.services.appointment_service import (
    AppointmentFieldError,
    ForbiddenStatusError,
    InvalidStatusError,
    book_appointment,
    change_status,
)
from dentacircle.services.audit_service import record as record_audit
from dentacircle.services.care_service import add_item, create_plan
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.patient_harness import login, patient_api
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 10, 17, 18, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]
_TODAY = _NOW.astimezone(_ZONE).date()


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    _SLOT["n"] = 0
    return throwaway_database_url


@pytest.fixture
def api(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with patient_api(throwaway_database_url, monkeypatch) as client:
        yield client


_SLOT = {"n": 0}
_PHONE = {"n": 1}


class _FrozenNow(datetime):
    """18:00 in Asia/Kolkata, so morning visits are arrived-today and already started."""

    @classmethod
    def now(cls, tz: TzInfo | None = None) -> datetime:
        fixed = datetime(2026, 10, 17, 12, 30, tzinfo=UTC)
        if tz is None:
            return fixed.replace(tzinfo=None)
        return fixed.astimezone(tz)


def test_a_date_creates_a_follow_up_with_no_open_items(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    visit_id = _in_progress(clinic_id, actor_id, patient_id, type_id)
    chosen = _TODAY + timedelta(days=12)
    _complete(clinic_id, actor_id, visit_id, chosen)
    _follow_id, appointment_id, status, due_on = _only(patient_id)
    assert appointment_id == visit_id
    assert status == "scheduled"
    assert due_on == chosen


def test_a_date_replaces_the_seven_day_default(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, patient_id)
    visit_id = _in_progress(clinic_id, actor_id, patient_id, type_id)
    chosen = _TODAY + timedelta(days=2)
    _complete(clinic_id, actor_id, visit_id, chosen)
    _patient_id, appointment_id, status, due_on = _only(patient_id)
    assert appointment_id == visit_id
    assert status == "scheduled"
    assert due_on == chosen
    assert due_on != _TODAY + timedelta(days=7)


def test_a_date_moves_an_existing_follow_up_and_keeps_its_status(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, patient_id)
    first = _in_progress(clinic_id, actor_id, patient_id, type_id)
    _complete(clinic_id, actor_id, first, None)
    original_id, _visit, _status, original_due = _only(patient_id)
    _set_status(original_id, "booked")
    second = _in_progress(clinic_id, actor_id, patient_id, type_id)
    chosen = _TODAY + timedelta(days=30)
    _complete(clinic_id, actor_id, second, chosen)
    rows = _rows(patient_id)
    assert len(rows) == 1
    follow_id, appointment_id, status, due_on = rows[0]
    assert follow_id == original_id
    assert status == "booked"
    assert due_on == chosen
    assert due_on != original_due
    assert appointment_id == second
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("follow_up", follow_id)
        updated = [event for event in events if event.action == "update"]
        assert updated[-1].changed_fields == ["appointment_id", "due_on"]
        assert updated[-1].actor_user_id == actor_id


def test_without_a_date_the_seven_day_rule_is_unchanged(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, patient_id)
    first = _in_progress(clinic_id, actor_id, patient_id, type_id)
    _complete(clinic_id, actor_id, first, None)
    follow_id, first_visit, status, due_on = _only(patient_id)
    assert first_visit == first
    assert status == "scheduled"
    assert due_on == _TODAY + timedelta(days=7)
    second = _in_progress(clinic_id, actor_id, patient_id, type_id)
    _complete(clinic_id, actor_id, second, None)
    again_id, appointment_id, again_status, again_due = _only(patient_id)
    assert again_id == follow_id
    assert again_status == "scheduled"
    assert again_due == due_on
    assert appointment_id == second
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("follow_up", follow_id)
        updated = next(event for event in events if event.action == "update")
        assert updated.changed_fields == ["appointment_id"]


def test_a_bad_date_or_a_date_on_another_status_does_not_move_the_visit(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    visit_id = _in_progress(clinic_id, actor_id, patient_id, type_id)
    for chosen in (_TODAY - timedelta(days=1), _TODAY + timedelta(days=366)):
        with Session(get_engine()) as session:
            with pytest.raises(AppointmentFieldError) as caught:
                change_status(
                    session,
                    clinic_id,
                    actor_id,
                    _ROLES,
                    visit_id,
                    "completed",
                    _NOW,
                    follow_up_due_on=chosen,
                )
            assert caught.value.field == "follow_up_due_on"
        assert _visit_status(visit_id) == "in_progress"
        assert _count(patient_id) == 0
    scheduled = _booked(clinic_id, actor_id, patient_id, type_id)
    for target in STATUS_TARGETS:
        if target == "completed":
            continue
        with Session(get_engine()) as session:
            with pytest.raises(AppointmentFieldError) as caught:
                change_status(
                    session,
                    clinic_id,
                    actor_id,
                    _ROLES,
                    scheduled,
                    target,
                    _NOW,
                    follow_up_due_on=_TODAY,
                )
            assert caught.value.code == "only_on_completed"
        assert _visit_status(scheduled) == "scheduled"
        assert _count(patient_id) == 0


def test_an_illegal_completion_is_refused_before_the_date(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    scheduled = _booked(clinic_id, actor_id, patient_id, type_id)
    with Session(get_engine()) as session:
        with pytest.raises(InvalidStatusError):
            change_status(
                session,
                clinic_id,
                actor_id,
                _ROLES,
                scheduled,
                "completed",
                _NOW,
                follow_up_due_on=_TODAY - timedelta(days=1),
            )
    assert _visit_status(scheduled) == "scheduled"
    assert _count(patient_id) == 0


def test_an_inactive_patient_completes_and_keeps_the_old_follow_up(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, patient_id)
    first = _in_progress(clinic_id, actor_id, patient_id, type_id)
    second = _in_progress(clinic_id, actor_id, patient_id, type_id)
    _complete(clinic_id, actor_id, first, _TODAY + timedelta(days=4))
    before = _only(patient_id)
    with Session(get_engine()) as session:
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
    _complete(clinic_id, actor_id, second, _TODAY + timedelta(days=9))
    assert _visit_status(second) == "completed"
    assert _rows(patient_id) == [before]


def test_a_role_that_cannot_complete_is_refused_before_the_date(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    visit_id = _in_progress(clinic_id, actor_id, patient_id, type_id)
    with Session(get_engine()) as session:
        with pytest.raises(ForbiddenStatusError):
            change_status(
                session,
                clinic_id,
                actor_id,
                ["receptionist"],
                visit_id,
                "completed",
                _NOW,
                follow_up_due_on=_TODAY - timedelta(days=1),
            )
    assert _visit_status(visit_id) == "in_progress"
    assert _count(patient_id) == 0


def test_a_failed_dated_write_or_audit_leaves_the_visit_in_progress(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    visit_id = _in_progress(clinic_id, actor_id, patient_id, type_id)
    before = _audit_count()

    def fail_add(self: FollowUpRepository, follow_up: FollowUp) -> None:
        raise IntegrityError("INSERT", {}, Exception("forced"))

    monkeypatch.setattr(FollowUpRepository, "add", fail_add)
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            change_status(
                session,
                clinic_id,
                actor_id,
                _ROLES,
                visit_id,
                "completed",
                _NOW,
                follow_up_due_on=_TODAY,
            )
    assert _visit_status(visit_id) == "in_progress"
    assert _count(patient_id) == 0
    assert _audit_count() == before
    monkeypatch.undo()

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
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            change_status(
                session,
                clinic_id,
                actor_id,
                _ROLES,
                visit_id,
                "completed",
                _NOW,
                follow_up_due_on=_TODAY,
            )
    assert _visit_status(visit_id) == "in_progress"
    assert _count(patient_id) == 0
    assert _audit_count() == before


def test_the_status_route_accepts_the_date_only_on_completion(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dentacircle.api.appointments.datetime", _FrozenNow)
    cookies = {"dc_session": login(api, "clinician@x.test")}
    chosen = _TODAY + timedelta(days=10)
    prior = {
        "arrived": "scheduled",
        "no_show": "scheduled",
        "in_progress": "arrived",
        "completed": "in_progress",
    }
    for target in STATUS_TARGETS:
        patient_id = _api_patient(api, cookies)
        visit_id = _api_visit(patient_id, prior[target])
        with_date = api.post(
            f"/appointments/{visit_id}/status",
            cookies=cookies,
            json={"status": target, "follow_up_due_on": chosen.isoformat()},
        )
        if target == "completed":
            assert with_date.status_code == 200
            assert set(with_date.json()) == {
                "id",
                "starts_at",
                "ends_at",
                "status",
                "patient",
                "clinician",
                "appointment_type",
            }
            assert with_date.json()["status"] == "completed"
            found = api.get(f"/patients/{patient_id}/follow-up", cookies=cookies)
            assert found.json()["follow_up"]["due_on"] == chosen.isoformat()
            assert found.json()["follow_up"]["appointment_id"] == visit_id
        else:
            assert with_date.status_code == 422
            assert "follow_up_due_on" in with_date.json()["error"]["message"]
            assert _api_status(visit_id) == prior[target]
        plain_id = _api_patient(api, cookies)
        plain_visit = _api_visit(plain_id, prior[target])
        plain = api.post(
            f"/appointments/{plain_visit}/status",
            cookies=cookies,
            json={"status": target},
        )
        assert plain.status_code == 200
        assert plain.json()["status"] == target
        assert "follow_up_due_on" not in plain.json()

    patient_id = _api_patient(api, cookies)
    visit_id = _api_visit(patient_id, "in_progress")
    bad = api.post(
        f"/appointments/{visit_id}/status",
        cookies=cookies,
        json={
            "status": "completed",
            "follow_up_due_on": (_TODAY - timedelta(days=1)).isoformat(),
        },
    )
    assert bad.status_code == 422
    assert "follow_up_due_on" in bad.json()["error"]["message"]
    assert _api_status(visit_id) == "in_progress"
    desk = {"dc_session": login(api, "receptionist@x.test")}
    denied = api.post(
        f"/appointments/{visit_id}/status",
        cookies=desk,
        json={
            "status": "completed",
            "follow_up_due_on": (_TODAY - timedelta(days=1)).isoformat(),
        },
    )
    assert denied.status_code == 403
    assert _api_status(visit_id) == "in_progress"
    stale = _api_visit(patient_id, "scheduled")
    conflict = api.post(
        f"/appointments/{stale}/status",
        cookies=cookies,
        json={
            "status": "completed",
            "follow_up_due_on": (_TODAY - timedelta(days=1)).isoformat(),
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "invalid_status"
    assert _api_status(stale) == "scheduled"


def _complete(clinic_id: UUID, actor_id: UUID, visit_id: UUID, due_on: date | None) -> None:
    with Session(get_engine()) as session:
        change_status(
            session,
            clinic_id,
            actor_id,
            _ROLES,
            visit_id,
            "completed",
            _NOW,
            follow_up_due_on=due_on,
        )
        session.commit()


def _in_progress(clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID) -> UUID:
    visit_id = _booked(clinic_id, actor_id, patient_id, type_id)
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "arrived", _NOW)
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "in_progress", _NOW)
        session.commit()
    return visit_id


def _booked(clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID) -> UUID:
    start = datetime(2026, 10, 17, 9, 0, tzinfo=_ZONE) + timedelta(minutes=30 * _SLOT["n"])
    _SLOT["n"] += 1
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            actor_id,
            type_id,
            start,
            start - timedelta(hours=1),
        )
        session.commit()
        return created.id


def _item(clinic_id: UUID, actor_id: UUID, patient_id: UUID) -> None:
    with Session(get_engine()) as session:
        plan = create_plan(session, clinic_id, actor_id, patient_id, "Sample plan")
        add_item(session, clinic_id, actor_id, plan.id, "Sample service")
        session.commit()


def _patient(clinic_id: UUID, actor_id: UUID) -> UUID:
    with Session(get_engine()) as session:
        patient = register_patient(
            session, clinic_id, actor_id, "Sample Ada", f"900000{_PHONE['n']:04d}", None
        )
        _PHONE["n"] += 1
        session.commit()
        return patient.id


def _clinic() -> tuple[UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "a@x.test",
            "Synthetic Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        return clinic.id, actor.id, consultation.id


def _only(patient_id: UUID) -> tuple[UUID, UUID | None, str, date]:
    rows = _rows(patient_id)
    assert len(rows) == 1
    return rows[0]


def _rows(patient_id: UUID) -> list[tuple[UUID, UUID | None, str, date]]:
    with Session(get_engine()) as session:
        found = session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)).all()
        return [(row.id, row.appointment_id, row.status, row.due_on) for row in found]


def _count(patient_id: UUID) -> int:
    return len(_rows(patient_id))


def _visit_status(visit_id: UUID) -> str:
    with Session(get_engine()) as session:
        visit = session.get(Appointment, visit_id)
        assert visit is not None
        return visit.status


def _set_status(follow_up_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE follow_up SET status = :status WHERE id = :id"),
            {"status": status, "id": follow_up_id},
        )
        session.commit()


def _audit_count() -> int:
    with Session(get_engine()) as session:
        found = session.scalar(select(func.count()).select_from(AuditEvent))
    return int(found or 0)


def _api_patient(api: TestClient, cookies: dict[str, str]) -> str:
    phone = f"910000{_PHONE['n']:04d}"
    _PHONE["n"] += 1
    response = api.post(
        "/patients",
        cookies=cookies,
        json={"full_name": "Sample Ada", "phone": phone},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _api_visit(patient_id: str, status: str) -> str:
    from uuid import uuid4

    from dentacircle.models.app_user import AppUser
    from dentacircle.repositories.appointment_repository import AppointmentRepository

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
        visit_id = uuid4()
        start = datetime(2026, 10, 17, 9, 0, tzinfo=_ZONE) + timedelta(minutes=30 * _SLOT["n"])
        _SLOT["n"] += 1
        AppointmentRepository(session, clinician.clinic_id).add(
            Appointment(
                id=visit_id,
                patient_id=UUID(patient_id),
                clinician_user_id=clinician.id,
                appointment_type_id=consultation.id,
                starts_at=start,
                ends_at=start + timedelta(minutes=30),
                status=status,
            )
        )
        session.commit()
        return str(visit_id)


def _api_status(visit_id: str) -> str:
    return _visit_status(UUID(visit_id))
