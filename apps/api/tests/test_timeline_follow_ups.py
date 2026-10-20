"""Each follow-up step writes its kind. Removing the call fails that test."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.services.appointment_service import cancel_appointment
from dentacircle.services.care_service import add_item, create_plan
from dentacircle.services.follow_up_service import (
    book_follow_up,
    cancel_follow_up,
    create_manual_follow_up,
    mark_contacted,
)
from tests.timeline_support import AT_START, NOW, World, book, kinds, later, move, world

pytest_plugins = ["tests.timeline_support"]


def test_a_manual_follow_up_records_follow_up_created(database: str) -> None:
    clinic = world()
    _manual(clinic)
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "follow_up_created"


def test_completing_with_an_open_item_records_follow_up_created(database: str) -> None:
    clinic = world()
    _open_item(clinic)
    _complete_visit(clinic, AT_START)
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == [
        "visit_completed",
        "follow_up_created",
    ]


def test_a_later_completion_records_follow_up_updated(database: str) -> None:
    clinic = world()
    _open_item(clinic)
    _complete_visit(clinic, AT_START)
    _complete_visit(clinic, later(60))
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == [
        "visit_completed",
        "follow_up_updated",
    ]


def test_mark_contacted_records_follow_up_contacted(database: str) -> None:
    clinic = world()
    follow_up_id = _manual(clinic)
    with Session(get_engine()) as session:
        mark_contacted(session, clinic.clinic_id, clinic.actor_id, follow_up_id, NOW)
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "follow_up_contacted"


def test_booking_records_follow_up_booked(database: str) -> None:
    clinic = world()
    follow_up_id = _manual(clinic)
    with Session(get_engine()) as session:
        book_follow_up(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            follow_up_id,
            clinic.clinician_id,
            clinic.consultation_id,
            AT_START,
            NOW,
        )
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == ["visit_booked", "follow_up_booked"]


def test_completing_the_booked_visit_records_follow_up_completed(database: str) -> None:
    clinic = world()
    _open_item(clinic)
    follow_up_id = _manual(clinic)
    visit_id = _book_follow_up(clinic, follow_up_id, AT_START)
    move(clinic, visit_id, "arrived")
    move(clinic, visit_id, "in_progress")
    move(clinic, visit_id, "completed")
    written = kinds(clinic.clinic_id, clinic.patient_id)
    assert written[-3:] == ["visit_completed", "follow_up_completed", "follow_up_created"]


def test_cancelling_the_booked_visit_records_follow_up_released(database: str) -> None:
    clinic = world()
    follow_up_id = _manual(clinic)
    visit_id = _book_follow_up(clinic, follow_up_id, AT_START)
    with Session(get_engine()) as session:
        cancel_appointment(session, clinic.clinic_id, clinic.actor_id, visit_id, NOW)
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == [
        "visit_cancelled",
        "follow_up_released",
    ]


def test_no_show_on_the_booked_visit_records_follow_up_released(database: str) -> None:
    clinic = world()
    follow_up_id = _manual(clinic)
    visit_id = _book_follow_up(clinic, follow_up_id, AT_START)
    move(clinic, visit_id, "no_show", now=AT_START)
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == [
        "visit_no_show",
        "follow_up_released",
    ]


def test_cancel_records_follow_up_cancelled(database: str) -> None:
    clinic = world()
    follow_up_id = _manual(clinic)
    with Session(get_engine()) as session:
        cancel_follow_up(session, clinic.clinic_id, clinic.actor_id, follow_up_id)
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "follow_up_cancelled"


def _manual(clinic: World) -> UUID:
    with Session(get_engine()) as session:
        row = create_manual_follow_up(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            NOW.date(),
            NOW,
        )
        session.commit()
        return row.id


def _open_item(clinic: World) -> None:
    with Session(get_engine()) as session:
        plan = create_plan(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "Sample plan"
        )
        add_item(session, clinic.clinic_id, clinic.actor_id, plan.id, "Root canal")
        session.commit()


def _complete_visit(clinic: World, start: datetime) -> None:
    visit_id = book(clinic, start)
    move(clinic, visit_id, "arrived")
    move(clinic, visit_id, "in_progress")
    move(clinic, visit_id, "completed")


def _book_follow_up(clinic: World, follow_up_id: UUID, start: datetime) -> UUID:
    with Session(get_engine()) as session:
        visit = book_follow_up(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            follow_up_id,
            clinic.clinician_id,
            clinic.consultation_id,
            start,
            NOW,
        )
        session.commit()
        return visit.id
