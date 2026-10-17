"""Completing a visit writes one follow-up when the patient still has open care."""

from datetime import UTC, date, datetime, timedelta
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
from dentacircle.repositories.follow_up_repository import FollowUpRepository
from dentacircle.services.appointment_service import (
    book_appointment,
    cancel_appointment,
    change_status,
    reschedule_appointment,
)
from dentacircle.services.care_service import add_item, change_item_status, create_plan
from dentacircle.services.care_session_service import record_session
from dentacircle.services.follow_up_service import get_open_follow_up
from dentacircle.services.patient_service import (
    PatientNotFoundError,
    register_patient,
    set_patient_status,
)
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_ORIGIN = datetime(2026, 10, 17, 10, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]
# Written here. Dropping a status from the open-item rule must fail the item test.
_ITEM_STATUSES = ("planned", "started", "completed", "cancelled")
_OPEN_ITEMS = {"planned", "started"}
# Written here. A visit move other than completed must not create a follow-up.
_TRIGGERS = {
    "arrived": False,
    "in_progress": False,
    "no_show": False,
    "cancel": False,
    "reschedule": False,
    "care_session": False,
    "item_status": False,
    "completed": True,
}
_OPEN_FOLLOW_UPS = ("scheduled", "contacted", "booked")
_CLOSED_FOLLOW_UPS = ("completed", "cancelled")


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    _SLOT["n"] = 0
    _PHONE["n"] = 1
    return throwaway_database_url


_SLOT = {"n": 0}
_PHONE = {"n": 1}


def test_completion_creates_one_follow_up_and_leaves_the_visit_view(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, patient_id, "planned")
    visit_id, start = _book(clinic_id, actor_id, patient_id, type_id)
    _move(clinic_id, actor_id, visit_id, "in_progress", start)
    completed_at = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    with Session(get_engine()) as session:
        view = change_status(
            session, clinic_id, actor_id, _ROLES, visit_id, "completed", completed_at
        )
        session.commit()
    assert view.id == visit_id
    assert view.status == "completed"
    assert view.patient.id == patient_id
    row = _only(clinic_id)
    assert row.patient_id == patient_id
    assert row.appointment_id == visit_id
    assert row.status == "scheduled"
    assert row.due_on == date(2026, 10, 18) + timedelta(days=7)


def test_nothing_open_writes_nothing(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    empty = _patient(clinic_id, actor_id)
    _complete(clinic_id, actor_id, empty, type_id)
    assert _count(clinic_id) == 0
    finished = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, finished, "completed")
    _item(clinic_id, actor_id, finished, "cancelled")
    _complete(clinic_id, actor_id, finished, type_id)
    assert _count(clinic_id) == 0


def test_open_items_count_across_the_patient_with_or_without_a_session(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    untouched = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, untouched, "completed")
    _item(clinic_id, actor_id, untouched, "planned")
    _complete(clinic_id, actor_id, untouched, type_id)
    assert _count(clinic_id) == 1

    recorded = _patient(clinic_id, actor_id)
    done_id = _item(clinic_id, actor_id, recorded, "planned")
    _item(clinic_id, actor_id, recorded, "planned")
    visit_id, start = _book(clinic_id, actor_id, recorded, type_id)
    _move(clinic_id, actor_id, visit_id, "arrived", start)
    with Session(get_engine()) as session:
        record_session(session, clinic_id, actor_id, visit_id, [(done_id, "completed")])
        session.commit()
    assert _count(clinic_id) == 1
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "in_progress", start)
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", start)
        session.commit()
    assert _count(clinic_id) == 2


def test_every_item_status(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    for status in _ITEM_STATUSES:
        patient_id = _patient(clinic_id, actor_id)
        _item(clinic_id, actor_id, patient_id, status)
        before = _count(clinic_id)
        _complete(clinic_id, actor_id, patient_id, type_id)
        created = _count(clinic_id) - before
        assert created == (1 if status in _OPEN_ITEMS else 0)


def test_an_open_follow_up_is_updated_and_a_closed_one_is_left_alone(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    for status in _OPEN_FOLLOW_UPS:
        patient_id = _patient(clinic_id, actor_id)
        _item(clinic_id, actor_id, patient_id, "planned")
        _first, _start = _book(clinic_id, actor_id, patient_id, type_id)
        kept = _complete(clinic_id, actor_id, patient_id, type_id)
        original = _only_for(patient_id)
        if status != "scheduled":
            _set_status(original.id, status)
        again = _complete(clinic_id, actor_id, patient_id, type_id)
        rows = _rows_for(patient_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.id == original.id
        assert row.status == status
        assert row.due_on == original.due_on
        assert row.appointment_id == again
        assert row.appointment_id != kept
    for status in _CLOSED_FOLLOW_UPS:
        patient_id = _patient(clinic_id, actor_id)
        _item(clinic_id, actor_id, patient_id, "started")
        closed_visit = _complete(clinic_id, actor_id, patient_id, type_id)
        closed = _only_for(patient_id)
        _set_status(closed.id, status)
        opened = _complete(clinic_id, actor_id, patient_id, type_id)
        rows = _rows_for(patient_id)
        assert len(rows) == 2
        still_closed = next(row for row in rows if row.id == closed.id)
        fresh = next(row for row in rows if row.id != closed.id)
        assert still_closed.status == status
        assert still_closed.appointment_id == closed_visit
        assert fresh.status == "scheduled"
        assert fresh.appointment_id == opened


def test_an_inactive_patient_completes_with_no_follow_up(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, patient_id, "planned")
    visit_id, start = _book(clinic_id, actor_id, patient_id, type_id)
    _move(clinic_id, actor_id, visit_id, "in_progress", start)
    with Session(get_engine()) as session:
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", start)
        session.commit()
    assert _count(clinic_id) == 0
    with Session(get_engine()) as session:
        visit = session.get(Appointment, visit_id)
        assert visit is not None
        assert visit.status == "completed"


def test_only_completion_writes_a_follow_up(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    for action, creates in _TRIGGERS.items():
        patient_id = _patient(clinic_id, actor_id)
        item_id = _item(clinic_id, actor_id, patient_id, "planned")
        before = _count(clinic_id)
        _trigger(clinic_id, actor_id, patient_id, type_id, item_id, action)
        assert (_count(clinic_id) - before) == (1 if creates else 0)


def test_a_failed_follow_up_write_leaves_the_visit_in_progress(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic_id, actor_id, type_id = _clinic()
    patient_id = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, patient_id, "planned")
    visit_id, start = _book(clinic_id, actor_id, patient_id, type_id)
    _move(clinic_id, actor_id, visit_id, "in_progress", start)
    before = _audit_count()

    def fail(self: FollowUpRepository, follow_up: FollowUp) -> None:
        raise IntegrityError("INSERT", {}, Exception("forced"))

    monkeypatch.setattr(FollowUpRepository, "add", fail)
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", start)
    with Session(get_engine()) as session:
        visit = session.get(Appointment, visit_id)
        assert visit is not None
        assert visit.status == "in_progress"
    assert _count(clinic_id) == 0
    assert _audit_count() == before


def test_another_clinic_is_not_read_or_written(database: str) -> None:
    clinic_id, actor_id, type_id = _clinic()
    other_id, other_actor, other_type = _clinic("Other Clinic", "b@x.test")
    other_patient = _patient(other_id, other_actor, "9000000099")
    _item(other_id, other_actor, other_patient, "planned")
    other_visit = _complete(other_id, other_actor, other_patient, other_type)
    before = _only(other_id)
    patient_id = _patient(clinic_id, actor_id)
    _item(clinic_id, actor_id, patient_id, "planned")
    _complete(clinic_id, actor_id, patient_id, type_id)
    after = _only(other_id)
    assert after.id == before.id
    assert after.appointment_id == other_visit
    assert after.status == before.status
    assert after.due_on == before.due_on
    assert _only(clinic_id).clinic_id == clinic_id
    with Session(get_engine()) as session:
        with pytest.raises(PatientNotFoundError):
            get_open_follow_up(session, clinic_id, other_patient)
        missing = get_open_follow_up(session, clinic_id, patient_id)
        assert missing is not None
        assert missing.patient_id == patient_id


def _trigger(
    clinic_id: UUID,
    actor_id: UUID,
    patient_id: UUID,
    type_id: UUID,
    item_id: UUID,
    action: str,
) -> None:
    if action == "item_status":
        with Session(get_engine()) as session:
            change_item_status(session, clinic_id, actor_id, item_id, "started")
            session.commit()
        return
    visit_id, start = _book(clinic_id, actor_id, patient_id, type_id)
    if action == "cancel":
        with Session(get_engine()) as session:
            cancel_appointment(session, clinic_id, actor_id, visit_id, start)
            session.commit()
        return
    if action == "reschedule":
        with Session(get_engine()) as session:
            reschedule_appointment(
                session,
                clinic_id,
                actor_id,
                visit_id,
                start + timedelta(hours=1),
                None,
                start,
            )
            session.commit()
        return
    if action == "no_show":
        _move(clinic_id, actor_id, visit_id, "no_show", start)
        return
    if action == "care_session":
        _move(clinic_id, actor_id, visit_id, "arrived", start)
        with Session(get_engine()) as session:
            record_session(session, clinic_id, actor_id, visit_id, [(item_id, "started")])
            session.commit()
        return
    _move(clinic_id, actor_id, visit_id, action, start)


def _complete(clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID) -> UUID:
    visit_id, start = _book(clinic_id, actor_id, patient_id, type_id)
    _move(clinic_id, actor_id, visit_id, "completed", start)
    return visit_id


def _move(clinic_id: UUID, actor_id: UUID, visit_id: UUID, status: str, now: datetime) -> None:
    with Session(get_engine()) as session:
        if status == "no_show":
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "no_show", now)
        else:
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "arrived", now)
            if status in ("in_progress", "completed"):
                change_status(session, clinic_id, actor_id, _ROLES, visit_id, "in_progress", now)
            if status == "completed":
                change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", now)
        session.commit()


def _book(
    clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID
) -> tuple[UUID, datetime]:
    start = _next_start()
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
        return created.id, start


def _next_start() -> datetime:
    while True:
        start = _ORIGIN + timedelta(days=_SLOT["n"])
        _SLOT["n"] += 1
        if start.weekday() != 6:
            return start


def _item(clinic_id: UUID, actor_id: UUID, patient_id: UUID, status: str) -> UUID:
    with Session(get_engine()) as session:
        plan = create_plan(session, clinic_id, actor_id, patient_id, "Sample plan")
        item = add_item(session, clinic_id, actor_id, plan.id, "Sample service")
        if status != "planned":
            change_item_status(session, clinic_id, actor_id, item.id, status)
        session.commit()
        return item.id


def _patient(clinic_id: UUID, actor_id: UUID, phone: str | None = None) -> UUID:
    if phone is None:
        phone = f"900000{_PHONE['n']:04d}"
        _PHONE["n"] += 1
    with Session(get_engine()) as session:
        patient = register_patient(session, clinic_id, actor_id, "Sample Ada", phone, None)
        session.commit()
        return patient.id


def _clinic(name: str = "Synthetic Clinic", email: str = "a@x.test") -> tuple[UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, name)
        actor = create_user(
            session,
            clinic.id,
            email,
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


def _only(clinic_id: UUID) -> FollowUp:
    rows = _scoped(clinic_id)
    assert len(rows) == 1
    return rows[0]


def _only_for(patient_id: UUID) -> FollowUp:
    rows = _rows_for(patient_id)
    assert len(rows) == 1
    return rows[0]


def _rows_for(patient_id: UUID) -> list[FollowUp]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)).all()
        )


def _scoped(clinic_id: UUID) -> list[FollowUp]:
    with Session(get_engine()) as session:
        return list(session.scalars(select(FollowUp).where(FollowUp.clinic_id == clinic_id)).all())


def _count(clinic_id: UUID) -> int:
    with Session(get_engine()) as session:
        found = session.scalar(
            select(func.count()).select_from(FollowUp).where(FollowUp.clinic_id == clinic_id)
        )
    return int(found or 0)


def _set_status(follow_up_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE follow_up SET status = :status WHERE id = :id"),
            {"status": status, "id": follow_up_id},
        )
        session.commit()


def _audit_count() -> int:
    with Session(get_engine()) as session:
        found = session.scalar(select(func.count()).select_from(text("audit_event")))
    return int(found or 0)
