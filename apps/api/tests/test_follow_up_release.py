"""Cancelling or missing the booked visit returns that follow-up to contacted."""

from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.follow_up import FollowUp
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.appointment_service import (
    book_appointment,
    cancel_appointment,
    change_status,
    reschedule_appointment,
)
from dentacircle.services.audit_service import record as record_audit
from dentacircle.services.follow_up_service import (
    FollowUpOpenError,
    book_follow_up,
    create_manual_follow_up,
    list_follow_ups,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_BEFORE = datetime(2026, 10, 20, 9, 0, tzinfo=_ZONE)
_START = datetime(2026, 10, 20, 10, 0, tzinfo=_ZONE)
_OTHER = datetime(2026, 10, 20, 11, 0, tzinfo=_ZONE)
_MOVED = datetime(2026, 10, 20, 16, 0, tzinfo=_ZONE)
_NOW = datetime(2026, 10, 20, 15, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]
_TODAY = date(2026, 10, 20)
_FUTURE = date(2026, 10, 22)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_cancelling_the_booked_visit_returns_it_to_the_due_view(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    follow_up_id, visit_id = _booked(clinic_id, actor_id, patient_id, type_id, _TODAY)
    _set_due_on(follow_up_id, date(2026, 10, 19))
    with Session(get_engine()) as session:
        cancel_appointment(session, clinic_id, actor_id, visit_id, _NOW)
        session.commit()
    row = _only(patient_id)
    assert row.id == follow_up_id
    assert row.status == "contacted"
    assert row.due_on == date(2026, 10, 19)
    assert row.booked_appointment_id == visit_id
    assert _visit_status(visit_id) == "cancelled"
    assert _due_ids(clinic_id) == [follow_up_id]
    _assert_release_audit(clinic_id, actor_id, follow_up_id)


def test_a_later_due_date_stays_out_of_the_due_view(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    follow_up_id, visit_id = _booked(clinic_id, actor_id, patient_id, type_id, _FUTURE)
    with Session(get_engine()) as session:
        cancel_appointment(session, clinic_id, actor_id, visit_id, _NOW)
        session.commit()
    assert _due_ids(clinic_id) == []
    assert _all_ids(clinic_id) == [follow_up_id]
    assert _only(patient_id).status == "contacted"


def test_cancelling_another_visit_leaves_the_follow_up_booked(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    follow_up_id, visit_id = _booked(clinic_id, actor_id, patient_id, type_id, _TODAY)
    other_id = _plain_visit(clinic_id, actor_id, patient_id, type_id)
    with Session(get_engine()) as session:
        cancel_appointment(session, clinic_id, actor_id, other_id, _NOW)
        session.commit()
    row = _only(patient_id)
    assert row.id == follow_up_id
    assert row.status == "booked"
    assert row.booked_appointment_id == visit_id
    assert _visit_status(visit_id) == "scheduled"
    assert _visit_status(other_id) == "cancelled"


def test_a_no_show_releases_the_follow_up_the_same_way(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    follow_up_id, visit_id = _booked(clinic_id, actor_id, patient_id, type_id, _TODAY)
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "no_show", _NOW)
        session.commit()
    row = _only(patient_id)
    assert row.id == follow_up_id
    assert row.status == "contacted"
    assert row.due_on == _TODAY
    assert row.booked_appointment_id == visit_id
    assert _visit_status(visit_id) == "no_show"
    assert _due_ids(clinic_id) == [follow_up_id]
    _assert_release_audit(clinic_id, actor_id, follow_up_id)


def test_reschedule_keeps_the_follow_up_booked(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    follow_up_id, visit_id = _booked(clinic_id, actor_id, patient_id, type_id, _TODAY)
    with Session(get_engine()) as session:
        moved = reschedule_appointment(session, clinic_id, actor_id, visit_id, _MOVED, None, _NOW)
        session.commit()
    assert moved.id == visit_id
    assert moved.starts_at == _MOVED
    row = _only(patient_id)
    assert row.id == follow_up_id
    assert row.status == "booked"
    assert row.booked_appointment_id == visit_id


def test_a_released_follow_up_is_still_the_open_row(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    _follow_up_id, visit_id = _booked(clinic_id, actor_id, patient_id, type_id, _TODAY)
    with Session(get_engine()) as session:
        cancel_appointment(session, clinic_id, actor_id, visit_id, _NOW)
        session.commit()
    with Session(get_engine()) as session:
        with pytest.raises(FollowUpOpenError):
            create_manual_follow_up(session, clinic_id, actor_id, patient_id, _FUTURE, _NOW)


def test_a_failed_release_audit_rolls_back_the_cancellation(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    follow_up_id, visit_id = _booked(clinic_id, actor_id, patient_id, type_id, _TODAY)
    before = _audit_count()
    monkeypatch.setattr(
        "dentacircle.services.follow_up_service.record", _fail_follow_up_status_change
    )
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            cancel_appointment(session, clinic_id, actor_id, visit_id, _NOW)
    assert _visit_status(visit_id) == "scheduled"
    row = _only(patient_id)
    assert row.id == follow_up_id
    assert row.status == "booked"
    assert _audit_count() == before


def _fail_follow_up_status_change(
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


def _assert_release_audit(clinic_id: UUID, actor_id: UUID, follow_up_id: UUID) -> None:
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("follow_up", follow_up_id)
        changed = [event for event in events if event.action == "status_change"]
        assert changed[-1].changed_fields == ["status"]
        assert changed[-1].actor_user_id == actor_id
        stored = " ".join(
            str(value)
            for row in session.execute(text("SELECT * FROM audit_event")).mappings()
            for value in row.values()
        )
    assert "Sample Ada" not in stored
    assert "contacted" not in stored
    assert "cancelled" not in stored


def _booked(
    clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID, due_on: date
) -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        created = create_manual_follow_up(session, clinic_id, actor_id, patient_id, due_on, _BEFORE)
        visit = book_follow_up(
            session,
            clinic_id,
            actor_id,
            created.id,
            actor_id,
            type_id,
            _START,
            _BEFORE,
        )
        session.commit()
    return created.id, visit.id


def _plain_visit(clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID) -> UUID:
    with Session(get_engine()) as session:
        created = book_appointment(
            session, clinic_id, actor_id, patient_id, actor_id, type_id, _OTHER, _BEFORE
        )
        session.commit()
    return created.id


def _due_ids(clinic_id: UUID) -> list[UUID]:
    with Session(get_engine()) as session:
        page = list_follow_ups(session, clinic_id, "due", 1, 20, _NOW)
    return [item.id for item in page.items]


def _all_ids(clinic_id: UUID) -> list[UUID]:
    with Session(get_engine()) as session:
        page = list_follow_ups(session, clinic_id, "all", 1, 20, _NOW)
    return [item.id for item in page.items]


def _world() -> tuple[UUID, UUID, UUID, UUID]:
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
        patient = register_patient(session, clinic.id, actor.id, "Sample Ada", "9000000001", None)
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        return clinic.id, actor.id, patient.id, consultation.id


def _only(patient_id: UUID) -> FollowUp:
    with Session(get_engine()) as session:
        rows = list(session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)))
    assert len(rows) == 1
    return rows[0]


def _visit_status(visit_id: UUID) -> str:
    with Session(get_engine()) as session:
        visit = session.get(Appointment, visit_id)
    assert visit is not None
    return visit.status


def _set_due_on(follow_up_id: UUID, due_on: date) -> None:
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE follow_up SET due_on = :due_on WHERE id = :id"),
            {"due_on": due_on, "id": follow_up_id},
        )
        session.commit()


def _audit_count() -> int:
    with Session(get_engine()) as session:
        found = session.scalar(select(func.count()).select_from(text("audit_event")))
    return int(found or 0)
