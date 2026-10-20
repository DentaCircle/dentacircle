"""Completing the booked visit closes that follow-up before a new one is written."""

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
from dentacircle.services.appointment_service import book_appointment, change_status
from dentacircle.services.audit_service import record as record_audit
from dentacircle.services.care_service import add_item, create_plan
from dentacircle.services.follow_up_service import (
    FollowUpOpenError,
    book_follow_up,
    create_manual_follow_up,
)
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_BEFORE = datetime(2026, 10, 20, 9, 0, tzinfo=_ZONE)
_NOW = datetime(2026, 10, 20, 15, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]
_CHOSEN = date(2026, 10, 25)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    _PHONE["n"] = 1
    _SLOT["n"] = 0
    return throwaway_database_url


_PHONE = {"n": 1}
_SLOT = {"n": 0}


def test_completing_the_booked_visit_closes_it_then_schedules_the_next(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _clinic_patient(with_item=True)
    follow_up_id, visit_id, due_on = _booked(clinic_id, actor_id, patient_id, type_id)
    _complete(clinic_id, actor_id, visit_id)
    rows = _rows(patient_id)
    assert len(rows) == 2
    closed = next(row for row in rows if row.id == follow_up_id)
    fresh = next(row for row in rows if row.id != follow_up_id)
    assert closed.status == "completed"
    assert closed.due_on == due_on
    assert closed.booked_appointment_id == visit_id
    assert closed.appointment_id is None
    assert fresh.status == "scheduled"
    assert fresh.due_on == date(2026, 10, 27)
    assert fresh.appointment_id == visit_id
    assert _visit_status(visit_id) == "completed"
    _assert_status_audit(clinic_id, actor_id, follow_up_id)


def test_a_clinician_date_is_the_new_follow_up(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _clinic_patient()
    follow_up_id, visit_id, _due_on = _booked(clinic_id, actor_id, patient_id, type_id)
    _complete(clinic_id, actor_id, visit_id, follow_up_due_on=_CHOSEN)
    rows = _rows(patient_id)
    fresh = next(row for row in rows if row.id != follow_up_id)
    assert fresh.status == "scheduled"
    assert fresh.due_on == _CHOSEN
    assert fresh.appointment_id == visit_id
    assert next(row for row in rows if row.id == follow_up_id).status == "completed"


def test_completing_another_visit_keeps_the_booked_follow_up(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _clinic_patient(with_item=True)
    follow_up_id, visit_id, due_on = _booked(clinic_id, actor_id, patient_id, type_id)
    other_id = _other_visit(clinic_id, actor_id, patient_id, type_id)
    _complete(clinic_id, actor_id, other_id)
    rows = _rows(patient_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.id == follow_up_id
    assert row.status == "booked"
    assert row.booked_appointment_id == visit_id
    assert row.appointment_id == other_id
    assert row.due_on == due_on


def test_scheduled_and_contacted_are_not_closed_by_completion(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    for status in ("scheduled", "contacted"):
        patient_id = _patient(clinic_id, actor_id)
        _item(clinic_id, actor_id, patient_id)
        follow_up_id, due_on = _scheduled(clinic_id, actor_id, patient_id)
        if status == "contacted":
            _set_status(follow_up_id, "contacted")
        visit_id = _other_visit(clinic_id, actor_id, patient_id, type_id)
        _complete(clinic_id, actor_id, visit_id)
        rows = _rows(patient_id)
        assert len(rows) == 1
        assert rows[0].id == follow_up_id
        assert rows[0].status == status
        assert rows[0].due_on == due_on
        assert rows[0].appointment_id == visit_id
        assert rows[0].booked_appointment_id is None


def test_a_closed_follow_up_is_not_touched(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    for status in ("completed", "cancelled"):
        patient_id = _patient(clinic_id, actor_id)
        _item(clinic_id, actor_id, patient_id)
        follow_up_id, due_on = _scheduled(clinic_id, actor_id, patient_id)
        visit_id = _other_visit(clinic_id, actor_id, patient_id, type_id)
        _set_closed(follow_up_id, status, visit_id)
        _complete(clinic_id, actor_id, visit_id)
        rows = _rows(patient_id)
        assert len(rows) == 2
        closed = next(row for row in rows if row.id == follow_up_id)
        fresh = next(row for row in rows if row.id != follow_up_id)
        assert closed.status == status
        assert closed.due_on == due_on
        assert closed.booked_appointment_id == visit_id
        assert closed.appointment_id is None
        assert fresh.status == "scheduled"
        assert fresh.appointment_id == visit_id


def test_an_inactive_patient_still_closes_and_gets_no_new_follow_up(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _clinic_patient(with_item=True)
    follow_up_id, visit_id, due_on = _booked(clinic_id, actor_id, patient_id, type_id)
    with Session(get_engine()) as session:
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
    _complete(clinic_id, actor_id, visit_id, follow_up_due_on=_CHOSEN)
    rows = _rows(patient_id)
    assert len(rows) == 1
    assert rows[0].id == follow_up_id
    assert rows[0].status == "completed"
    assert rows[0].due_on == due_on
    assert rows[0].booked_appointment_id == visit_id
    assert _visit_status(visit_id) == "completed"


def test_a_close_with_no_open_care_lets_a_new_follow_up_be_created(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _clinic_patient()
    _follow_up_id, visit_id, _due_on = _booked(clinic_id, actor_id, patient_id, type_id)
    _complete(clinic_id, actor_id, visit_id)
    assert [row.status for row in _rows(patient_id)] == ["completed"]
    with Session(get_engine()) as session:
        created = create_manual_follow_up(
            session, clinic_id, actor_id, patient_id, _NOW.date(), _NOW
        )
        session.commit()
    assert created.status == "scheduled"
    assert created.patient_id == patient_id


def test_a_failed_close_audit_rolls_back_the_visit(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic_id, actor_id, patient_id, type_id = _clinic_patient(with_item=True)
    follow_up_id, visit_id, _due_on = _booked(clinic_id, actor_id, patient_id, type_id)
    _to_in_progress(clinic_id, actor_id, visit_id)
    before = _audit_count()
    monkeypatch.setattr(
        "dentacircle.services.follow_up_service.record", _fail_follow_up_status_change
    )
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", _NOW)
    assert _visit_status(visit_id) == "in_progress"
    rows = _rows(patient_id)
    assert len(rows) == 1
    assert rows[0].id == follow_up_id
    assert rows[0].status == "booked"
    assert _audit_count() == before


def test_an_open_follow_up_still_blocks_a_second_one_after_another_visit(
    database: str,
) -> None:
    clinic_id, actor_id, patient_id, type_id = _clinic_patient(with_item=True)
    _booked(clinic_id, actor_id, patient_id, type_id)
    other_id = _other_visit(clinic_id, actor_id, patient_id, type_id)
    _complete(clinic_id, actor_id, other_id)
    with Session(get_engine()) as session:
        with pytest.raises(FollowUpOpenError):
            create_manual_follow_up(session, clinic_id, actor_id, patient_id, _NOW.date(), _NOW)


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


def _assert_status_audit(clinic_id: UUID, actor_id: UUID, follow_up_id: UUID) -> None:
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("follow_up", follow_up_id)
        changed = [event for event in events if event.action == "status_change"]
        assert [event.changed_fields for event in changed] == [
            ["status", "booked_appointment_id"],
            ["status"],
        ]
        assert changed[-1].actor_user_id == actor_id
        stored = " ".join(
            str(value)
            for row in session.execute(text("SELECT * FROM audit_event")).mappings()
            for value in row.values()
        )
    assert "Sample Ada" not in stored
    assert "completed" not in stored
    assert "scheduled" not in stored
    assert "contacted" not in stored


def _complete(
    clinic_id: UUID,
    actor_id: UUID,
    visit_id: UUID,
    follow_up_due_on: date | None = None,
) -> None:
    _to_in_progress(clinic_id, actor_id, visit_id)
    with Session(get_engine()) as session:
        change_status(
            session,
            clinic_id,
            actor_id,
            _ROLES,
            visit_id,
            "completed",
            _NOW,
            follow_up_due_on=follow_up_due_on,
        )
        session.commit()


def _to_in_progress(clinic_id: UUID, actor_id: UUID, visit_id: UUID) -> None:
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "arrived", _NOW)
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "in_progress", _NOW)
        session.commit()


def _booked(
    clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID
) -> tuple[UUID, UUID, date]:
    follow_up_id, due_on = _scheduled(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        visit = book_follow_up(
            session,
            clinic_id,
            actor_id,
            follow_up_id,
            actor_id,
            type_id,
            _next_slot(),
            _BEFORE,
        )
        session.commit()
    return follow_up_id, visit.id, due_on


def _scheduled(clinic_id: UUID, actor_id: UUID, patient_id: UUID) -> tuple[UUID, date]:
    with Session(get_engine()) as session:
        created = create_manual_follow_up(
            session, clinic_id, actor_id, patient_id, _NOW.date(), _BEFORE
        )
        session.commit()
    return created.id, created.due_on


def _other_visit(clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID) -> UUID:
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            actor_id,
            type_id,
            _next_slot(),
            _BEFORE,
        )
        session.commit()
    return created.id


def _item(clinic_id: UUID, actor_id: UUID, patient_id: UUID) -> None:
    with Session(get_engine()) as session:
        plan = create_plan(session, clinic_id, actor_id, patient_id, "Sample plan")
        add_item(session, clinic_id, actor_id, plan.id, "Sample service")
        session.commit()


def _clinic_patient(*, with_item: bool = False) -> tuple[UUID, UUID, UUID, UUID]:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    if with_item:
        _item(clinic_id, actor_id, patient_id)
    return clinic_id, actor_id, patient_id, type_id


def _patient(clinic_id: UUID, actor_id: UUID) -> UUID:
    phone = f"900000{_PHONE['n']:04d}"
    _PHONE["n"] += 1
    with Session(get_engine()) as session:
        patient = register_patient(session, clinic_id, actor_id, "Sample Ada", phone, None)
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


def _rows(patient_id: UUID) -> list[FollowUp]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)).all()
        )


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


def _set_closed(follow_up_id: UUID, status: str, visit_id: UUID) -> None:
    with Session(get_engine()) as session:
        session.execute(
            text(
                "UPDATE follow_up SET status = :status, booked_appointment_id = :visit "
                "WHERE id = :id"
            ),
            {"status": status, "visit": visit_id, "id": follow_up_id},
        )
        session.commit()


def _next_slot() -> datetime:
    index = _SLOT["n"]
    _SLOT["n"] += 1
    minutes = 10 * 60 + index * 30
    return datetime(2026, 10, 20, minutes // 60, minutes % 60, tzinfo=_ZONE)


def _audit_count() -> int:
    with Session(get_engine()) as session:
        found = session.scalar(select(func.count()).select_from(text("audit_event")))
    return int(found or 0)
