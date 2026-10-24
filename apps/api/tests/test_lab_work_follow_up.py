"""Marking lab work ready creates or pulls forward one follow-up. Other moves do not."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.follow_up import FollowUp
from dentacircle.services.follow_up_service import create_manual_follow_up
from dentacircle.services.lab_work_service import change_lab_status, create_lab_work
from dentacircle.services.patient_service import set_patient_status
from tests.timeline_support import NOW, World, kinds, world

pytest_plugins = ["tests.timeline_support"]

_TODAY = date(2026, 10, 12)
_LATER = date(2026, 10, 20)


def test_ready_creates_a_follow_up_due_today_when_none_is_open(database: str) -> None:
    clinic = world()
    lab_id = _lab(clinic)
    _move(clinic, lab_id, "ready")
    row = _only_follow_up(clinic.patient_id)
    assert row.status == "scheduled"
    assert row.due_on == _TODAY
    assert row.appointment_id is None
    created = [event for event in _audits("follow_up") if event.action == "create"]
    assert len(created) == 1
    assert created[0].changed_fields == []
    assert created[0].entity_id == row.id
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == [
        "follow_up_created",
        "lab_work_ready",
    ]


def test_ready_pulls_a_later_open_follow_up_to_today_and_keeps_its_status(database: str) -> None:
    clinic = world()
    follow_up_id = _manual(clinic, _LATER)
    _set_status(follow_up_id, "contacted")
    lab_id = _lab(clinic)
    before = _follow_up_audit_count()
    _move(clinic, lab_id, "ready")
    row = _only_follow_up(clinic.patient_id)
    assert row.id == follow_up_id
    assert row.status == "contacted"
    assert row.due_on == _TODAY
    updates = [event for event in _audits("follow_up") if event.action == "update"]
    assert len(updates) == 1
    assert updates[0].changed_fields == ["due_on"]
    assert _follow_up_audit_count() == before + 1
    assert "follow_up_updated" in kinds(clinic.clinic_id, clinic.patient_id)


def test_a_booked_or_already_due_follow_up_is_left_alone(database: str) -> None:
    clinic = world()
    booked_id = _manual(clinic, _LATER)
    _set_status(booked_id, "booked")
    lab_id = _lab(clinic)
    before = _follow_up_audit_count()
    _move(clinic, lab_id, "ready")
    booked = _only_follow_up(clinic.patient_id)
    assert booked.status == "booked"
    assert booked.due_on == _LATER
    assert _follow_up_audit_count() == before

    _move(clinic, lab_id, "collected")
    _set_status(booked_id, "scheduled", due_on=_TODAY)
    second = _lab(clinic, "Bridge")
    before = _follow_up_audit_count()
    _move(clinic, second, "ready")
    due = _only_follow_up(clinic.patient_id)
    assert due.status == "scheduled"
    assert due.due_on == _TODAY
    assert _follow_up_audit_count() == before


def test_an_inactive_patient_can_be_marked_ready_without_a_follow_up(database: str) -> None:
    clinic = world()
    lab_id = _lab(clinic)
    later_id = _manual(clinic, _LATER)
    with Session(get_engine()) as session:
        set_patient_status(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "inactive"
        )
        session.commit()
    before = _follow_up_audit_count()
    _move(clinic, lab_id, "ready")
    row = _only_follow_up(clinic.patient_id)
    assert row.id == later_id
    assert row.due_on == _LATER
    assert row.status == "scheduled"
    assert _follow_up_audit_count() == before


def test_collected_and_cancelled_do_not_touch_the_follow_up(database: str) -> None:
    clinic = world()
    lab_id = _lab(clinic)
    _move(clinic, lab_id, "ready")
    before = _follow_up_audit_count()
    due_on = _only_follow_up(clinic.patient_id).due_on
    _move(clinic, lab_id, "collected")
    assert _only_follow_up(clinic.patient_id).status == "scheduled"
    assert _only_follow_up(clinic.patient_id).due_on == due_on
    assert _follow_up_audit_count() == before

    second = _lab(clinic, "Bridge")
    _move(clinic, second, "cancelled")
    assert _only_follow_up(clinic.patient_id).status == "scheduled"
    assert _follow_up_audit_count() == before


def _lab(clinic: World, title: str = "Crown") -> UUID:
    with Session(get_engine()) as session:
        created = create_lab_work(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            title,
            _LATER,
            None,
            NOW,
        )
        session.commit()
        return created.id


def _move(clinic: World, lab_work_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        change_lab_status(session, clinic.clinic_id, clinic.actor_id, lab_work_id, status, NOW)
        session.commit()


def _manual(clinic: World, due_on: date) -> UUID:
    with Session(get_engine()) as session:
        created = create_manual_follow_up(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, due_on, NOW
        )
        session.commit()
        return created.id


def _set_status(follow_up_id: UUID, status: str, due_on: date | None = None) -> None:
    with Session(get_engine()) as session:
        row = session.get(FollowUp, follow_up_id)
        assert row is not None
        row.status = status
        if due_on is not None:
            row.due_on = due_on
        session.commit()


def _only_follow_up(patient_id: UUID) -> FollowUp:
    with Session(get_engine()) as session:
        rows = list(session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)))
    assert len(rows) == 1
    return rows[0]


def _audits(entity_type: str) -> list[AuditEvent]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(select(AuditEvent).where(AuditEvent.entity_type == entity_type))
        )


def _follow_up_audit_count() -> int:
    return len(_audits("follow_up"))
