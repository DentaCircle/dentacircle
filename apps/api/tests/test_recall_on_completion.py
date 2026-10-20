"""A completed visit writes one recall, and the booked visit closes or releases it."""

from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.recall import add_months
from dentacircle.models.appointment import Appointment
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.follow_up import FollowUp
from dentacircle.models.recall import Recall
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.appointment_service import (
    book_appointment,
    cancel_appointment,
    change_status,
    reschedule_appointment,
)
from dentacircle.services.appointment_type_service import (
    create_appointment_type,
    list_appointment_types,
    update_appointment_type,
)
from dentacircle.services.audit_service import record as record_audit
from dentacircle.services.care_service import add_item, create_plan
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_ROLES = ["clinician"]
_NOW = datetime(2026, 10, 21, 8, 0, tzinfo=_ZONE)
_UTC_EVENING = datetime(2026, 10, 20, 20, 30, tzinfo=ZoneInfo("UTC"))


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


def test_completing_a_ruled_visit_uses_the_clinic_local_day(database: str) -> None:
    clinic_id, actor_id, patient_id, scaling_id, _consultation_id = _world()
    visit_id = _book_at(clinic_id, actor_id, patient_id, scaling_id, _slot_on(_UTC_EVENING))
    _complete(clinic_id, actor_id, visit_id, _UTC_EVENING)
    row = _only(patient_id)
    assert row.status == "scheduled"
    assert row.due_on.isoformat() == "2027-04-21"
    assert row.appointment_type_id == scaling_id
    assert row.source_appointment_id == visit_id
    assert row.booked_appointment_id is None
    assert _visit_status(visit_id) == "completed"


def test_a_later_visit_moves_a_contacted_recall_and_keeps_its_status(database: str) -> None:
    clinic_id, actor_id, patient_id, scaling_id, _consultation_id = _world()
    first = _completed(clinic_id, actor_id, patient_id, scaling_id)
    recall_id = _only(patient_id).id
    _set_status(recall_id, "contacted")
    yearly_id = _yearly_type(clinic_id)
    other_id = _other_user(clinic_id)
    second = _completed(clinic_id, other_id, patient_id, yearly_id)
    row = _only(patient_id)
    assert row.id == recall_id
    assert row.status == "contacted"
    assert row.appointment_type_id == yearly_id
    assert row.source_appointment_id == second
    assert row.due_on == add_months(_local_day(second), 12)
    assert row.source_appointment_id != first


def test_a_booked_recall_is_not_moved_by_another_completion(database: str) -> None:
    clinic_id, actor_id, patient_id, scaling_id, consultation_id = _world()
    first = _completed(clinic_id, actor_id, patient_id, scaling_id)
    recall_id = _only(patient_id).id
    before = _only(patient_id)
    held = _book(clinic_id, actor_id, patient_id, consultation_id)
    _mark_booked(recall_id, held)
    _completed(clinic_id, actor_id, patient_id, scaling_id)
    row = _only(patient_id)
    assert row.id == recall_id
    assert row.status == "booked"
    assert row.due_on == before.due_on
    assert row.source_appointment_id == first
    assert row.appointment_type_id == scaling_id
    assert row.booked_appointment_id == held


def test_no_rule_inactive_cancel_and_no_show_write_nothing(database: str) -> None:
    clinic_id, actor_id, patient_id, scaling_id, consultation_id = _world()
    plain = _book(clinic_id, actor_id, patient_id, consultation_id)
    _complete_booked(clinic_id, actor_id, plain)
    assert _count(patient_id) == 0
    assert _visit_status(plain) == "completed"

    created = _completed(clinic_id, actor_id, patient_id, scaling_id)
    kept = _only(patient_id)
    later = _book(clinic_id, actor_id, patient_id, scaling_id)
    _set_patient_inactive(clinic_id, actor_id, patient_id)
    _complete_booked(clinic_id, actor_id, later)
    assert _count(patient_id) == 1
    assert _only(patient_id).due_on == kept.due_on
    assert _only(patient_id).source_appointment_id == created

    other_id = _patient(clinic_id, actor_id)
    cancelled = _book(clinic_id, actor_id, other_id, scaling_id)
    _cancel(clinic_id, actor_id, cancelled)
    missed, missed_at = _book_pair(clinic_id, actor_id, other_id, scaling_id)
    _no_show(clinic_id, actor_id, missed, missed_at + timedelta(minutes=30))
    assert _count(other_id) == 0


def test_a_completion_can_write_a_follow_up_a_recall_both_or_neither(database: str) -> None:
    clinic_id, actor_id, patient_id, scaling_id, consultation_id = _world()
    _item(clinic_id, actor_id, patient_id)
    both = _completed(clinic_id, actor_id, patient_id, scaling_id)
    assert _count(patient_id) == 1
    assert _follow_up_count(patient_id) == 1
    assert _only(patient_id).source_appointment_id == both

    quiet_id = _patient(clinic_id, actor_id)
    _complete_booked(clinic_id, actor_id, _book(clinic_id, actor_id, quiet_id, consultation_id))
    assert _count(quiet_id) == 0
    assert _follow_up_count(quiet_id) == 0

    followed_id = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, followed_id)
    _complete_booked(clinic_id, actor_id, _book(clinic_id, actor_id, followed_id, consultation_id))
    assert _count(followed_id) == 0
    assert _follow_up_count(followed_id) == 1


def test_create_and_move_are_audited_without_values(database: str) -> None:
    clinic_id, actor_id, patient_id, scaling_id, _consultation_id = _world()
    other_id = _other_user(clinic_id)
    _completed(clinic_id, actor_id, patient_id, scaling_id)
    recall_id = _only(patient_id).id
    with Session(get_engine()) as session:
        created = AuditRepository(session, clinic_id).list_for_entity("recall", recall_id)
        assert [(event.action, event.changed_fields, event.actor_user_id) for event in created] == [
            ("create", [], actor_id)
        ]
        assert "2027-04-21" not in _audit_text(session)
        assert "Sample Ada" not in _audit_text(session)
    _completed(clinic_id, other_id, patient_id, scaling_id)
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("recall", recall_id)
        updated = next(event for event in events if event.action == "update")
        assert updated.changed_fields == [
            "appointment_type_id",
            "source_appointment_id",
            "due_on",
        ]
        assert updated.actor_user_id == other_id


def test_a_failed_recall_audit_leaves_the_visit_uncompleted(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic_id, actor_id, patient_id, scaling_id, _consultation_id = _world()
    visit_id, starts_at = _book_pair(clinic_id, actor_id, patient_id, scaling_id)
    morning = _morning(starts_at)
    _to_in_progress(clinic_id, actor_id, visit_id, morning)
    before = _audit_count()
    monkeypatch.setattr("dentacircle.services.recall_service.record", _fail_recall_audit)
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", morning)
    assert _visit_status(visit_id) == "in_progress"
    assert _count(patient_id) == 0
    assert _audit_count() == before


def test_completing_the_booked_visit_closes_it_then_writes_a_new_recall(database: str) -> None:
    clinic_id, actor_id, patient_id, scaling_id, _consultation_id = _world()
    _completed(clinic_id, actor_id, patient_id, scaling_id)
    recall_id = _only(patient_id).id
    due_on = _only(patient_id).due_on
    second, starts_at = _book_pair(clinic_id, actor_id, patient_id, scaling_id)
    _mark_booked(recall_id, second)
    _complete(clinic_id, actor_id, second, _morning(starts_at))
    rows = _rows(patient_id)
    assert len(rows) == 2
    closed = next(row for row in rows if row.id == recall_id)
    fresh = next(row for row in rows if row.id != recall_id)
    assert closed.status == "completed"
    assert closed.due_on == due_on
    assert closed.booked_appointment_id == second
    assert fresh.status == "scheduled"
    assert fresh.due_on == add_months(starts_at.astimezone(_ZONE).date(), 6)
    assert fresh.source_appointment_id == second
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("recall", recall_id)
        assert ("status_change", ["status"]) in [
            (event.action, event.changed_fields) for event in events
        ]


def test_an_inactive_patient_still_closes_the_booked_recall(database: str) -> None:
    clinic_id, actor_id, patient_id, scaling_id, consultation_id = _world()
    _completed(clinic_id, actor_id, patient_id, scaling_id)
    recall_id = _only(patient_id).id
    second = _book(clinic_id, actor_id, patient_id, consultation_id)
    _mark_booked(recall_id, second)
    _set_patient_inactive(clinic_id, actor_id, patient_id)
    _complete_booked(clinic_id, actor_id, second)
    assert _count(patient_id) == 1
    assert _only(patient_id).status == "completed"
    assert _visit_status(second) == "completed"


def test_cancel_or_no_show_releases_the_booked_recall_and_reschedule_does_not(
    database: str,
) -> None:
    clinic_id, actor_id, patient_id, scaling_id, consultation_id = _world()
    _completed(clinic_id, actor_id, patient_id, scaling_id)
    recall_id = _only(patient_id).id
    due_on = _only(patient_id).due_on
    booked = _book(clinic_id, actor_id, patient_id, consultation_id)
    _mark_booked(recall_id, booked)
    other = _book(clinic_id, actor_id, patient_id, consultation_id)
    _cancel(clinic_id, actor_id, other)
    assert _only(patient_id).status == "booked"

    _cancel(clinic_id, actor_id, booked)
    released = _only(patient_id)
    assert released.status == "contacted"
    assert released.due_on == due_on
    assert released.booked_appointment_id == booked

    missed, missed_at = _book_pair(clinic_id, actor_id, patient_id, consultation_id)
    _mark_booked(recall_id, missed)
    _no_show(clinic_id, actor_id, missed, missed_at + timedelta(minutes=30))
    again = _only(patient_id)
    assert again.status == "contacted"
    assert again.booked_appointment_id == missed

    kept, kept_at = _book_pair(clinic_id, actor_id, patient_id, consultation_id)
    _mark_booked(recall_id, kept)
    _reschedule(clinic_id, actor_id, kept, kept_at + timedelta(hours=1))
    assert _only(patient_id).status == "booked"
    assert _only(patient_id).booked_appointment_id == kept
    assert _only(patient_id).due_on == due_on


def test_changing_the_rule_does_not_change_an_existing_recall(database: str) -> None:
    clinic_id, actor_id, patient_id, scaling_id, _consultation_id = _world()
    _completed(clinic_id, actor_id, patient_id, scaling_id)
    before = _only(patient_id).due_on
    with Session(get_engine()) as session:
        update_appointment_type(
            session,
            clinic_id,
            scaling_id,
            "Scaling",
            30,
            True,
            12,
            set_recall_after_months=True,
        )
        session.commit()
    assert _only(patient_id).due_on == before


def test_a_failed_close_audit_leaves_the_visit_unchanged(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic_id, actor_id, patient_id, scaling_id, consultation_id = _world()
    _completed(clinic_id, actor_id, patient_id, scaling_id)
    recall_id = _only(patient_id).id
    second, starts_at = _book_pair(clinic_id, actor_id, patient_id, consultation_id)
    _mark_booked(recall_id, second)
    morning = _morning(starts_at)
    _to_in_progress(clinic_id, actor_id, second, morning)
    monkeypatch.setattr("dentacircle.services.recall_service.record", _fail_recall_audit)
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            change_status(session, clinic_id, actor_id, _ROLES, second, "completed", morning)
    assert _visit_status(second) == "in_progress"
    assert _only(patient_id).status == "booked"


def _fail_recall_audit(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    entity_type: str,
    entity_id: UUID,
    action: str,
    changed_fields: list[str] | None = None,
) -> None:
    if entity_type == "recall":
        raise IntegrityError("INSERT", {}, Exception("forced"))
    record_audit(session, clinic_id, actor_user_id, entity_type, entity_id, action, changed_fields)


def _completed(clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID) -> UUID:
    visit_id, starts_at = _book_pair(clinic_id, actor_id, patient_id, type_id)
    _complete(clinic_id, actor_id, visit_id, _morning(starts_at))
    return visit_id


def _complete_booked(clinic_id: UUID, actor_id: UUID, visit_id: UUID) -> None:
    _complete(clinic_id, actor_id, visit_id, _morning(_starts(visit_id)))


def _complete(clinic_id: UUID, actor_id: UUID, visit_id: UUID, now: datetime) -> None:
    _to_in_progress(clinic_id, actor_id, visit_id, now)
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", now)
        session.commit()


def _to_in_progress(clinic_id: UUID, actor_id: UUID, visit_id: UUID, now: datetime) -> None:
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "arrived", now)
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "in_progress", now)
        session.commit()


def _cancel(clinic_id: UUID, actor_id: UUID, visit_id: UUID) -> None:
    with Session(get_engine()) as session:
        cancel_appointment(session, clinic_id, actor_id, visit_id, _NOW)
        session.commit()


def _no_show(clinic_id: UUID, actor_id: UUID, visit_id: UUID, now: datetime) -> None:
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "no_show", now)
        session.commit()


def _reschedule(clinic_id: UUID, actor_id: UUID, visit_id: UUID, starts_at: datetime) -> None:
    with Session(get_engine()) as session:
        reschedule_appointment(session, clinic_id, actor_id, visit_id, starts_at, None, _NOW)
        session.commit()


def _book(clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID) -> UUID:
    visit_id, _starts_at = _book_pair(clinic_id, actor_id, patient_id, type_id)
    return visit_id


def _book_pair(
    clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID
) -> tuple[UUID, datetime]:
    starts_at = _next_start()
    return _book_at(clinic_id, actor_id, patient_id, type_id, starts_at), starts_at


def _book_at(
    clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID, starts_at: datetime
) -> UUID:
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            actor_id,
            type_id,
            starts_at,
            _morning(starts_at),
        )
        session.commit()
    return created.id


def _mark_booked(recall_id: UUID, visit_id: UUID) -> None:
    with Session(get_engine()) as session:
        row = session.get(Recall, recall_id)
        assert row is not None
        row.status = "booked"
        row.booked_appointment_id = visit_id
        session.commit()


def _set_status(recall_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(Recall, recall_id)
        assert row is not None
        row.status = status
        session.commit()


def _set_patient_inactive(clinic_id: UUID, actor_id: UUID, patient_id: UUID) -> None:
    with Session(get_engine()) as session:
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()


def _item(clinic_id: UUID, actor_id: UUID, patient_id: UUID) -> None:
    with Session(get_engine()) as session:
        plan = create_plan(session, clinic_id, actor_id, patient_id, "Sample plan")
        add_item(session, clinic_id, actor_id, plan.id, "Sample service")
        session.commit()


def _yearly_type(clinic_id: UUID) -> UUID:
    with Session(get_engine()) as session:
        created = create_appointment_type(session, clinic_id, "Yearly review", 30, 12)
        session.commit()
    return created.id


def _world() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session, clinic.id, "clinician@x.test", "Synthetic Person", "hash-not-used", _ROLES
        )
        session.commit()
        clinic_id = clinic.id
        actor_id = actor.id
    patient_id = _patient(clinic_id, actor_id)
    with Session(get_engine()) as session:
        types = list_appointment_types(session, clinic_id, include_inactive=False)
    by_name = {item.name: item.id for item in types}
    return clinic_id, actor_id, patient_id, by_name["Scaling"], by_name["Consultation"]


def _other_user(clinic_id: UUID) -> UUID:
    with Session(get_engine()) as session:
        user = create_user(
            session, clinic_id, "other@x.test", "Synthetic Person", "hash-not-used", _ROLES
        )
        session.commit()
        return user.id


def _patient(clinic_id: UUID, actor_id: UUID) -> UUID:
    phone = f"900000{_PHONE['n']:04d}"
    _PHONE["n"] += 1
    with Session(get_engine()) as session:
        patient = register_patient(session, clinic_id, actor_id, "Sample Ada", phone, None)
        session.commit()
    return patient.id


def _next_start() -> datetime:
    index = _SLOT["n"]
    _SLOT["n"] += 1
    day = index // 4
    hour = 10 + (index % 4) * 2
    base = _NOW + timedelta(days=day)
    return base.replace(hour=hour, minute=0)


def _slot_on(now: datetime) -> datetime:
    local = now.astimezone(_ZONE)
    return datetime(local.year, local.month, local.day, 10, 0, tzinfo=_ZONE)


def _morning(starts_at: datetime) -> datetime:
    local = starts_at.astimezone(_ZONE)
    return datetime(local.year, local.month, local.day, 8, 0, tzinfo=_ZONE)


def _local_day(visit_id: UUID) -> date:
    return _starts(visit_id).astimezone(_ZONE).date()


def _starts(visit_id: UUID) -> datetime:
    with Session(get_engine()) as session:
        row = session.get(Appointment, visit_id)
        assert row is not None
        return row.starts_at


def _only(patient_id: UUID) -> Recall:
    rows = _rows(patient_id)
    assert len(rows) == 1
    return rows[0]


def _rows(patient_id: UUID) -> list[Recall]:
    with Session(get_engine()) as session:
        return list(session.scalars(select(Recall).where(Recall.patient_id == patient_id)).all())


def _count(patient_id: UUID) -> int:
    return len(_rows(patient_id))


def _follow_up_count(patient_id: UUID) -> int:
    with Session(get_engine()) as session:
        total = session.scalar(
            select(func.count()).select_from(FollowUp).where(FollowUp.patient_id == patient_id)
        )
    return int(total or 0)


def _visit_status(visit_id: UUID) -> str:
    with Session(get_engine()) as session:
        row = session.get(Appointment, visit_id)
        assert row is not None
        return row.status


def _audit_count() -> int:
    with Session(get_engine()) as session:
        total = session.scalar(select(func.count()).select_from(AuditEvent))
    return int(total or 0)


def _audit_text(session: Session) -> str:
    rows = session.scalars(select(AuditEvent)).all()
    return " ".join(
        " ".join([row.entity_type, row.action, " ".join(row.changed_fields or [])]) for row in rows
    )
