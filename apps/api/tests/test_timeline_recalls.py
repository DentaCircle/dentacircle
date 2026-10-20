"""Each recall step writes its kind. Removing the call fails that test."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.recall import Recall
from dentacircle.services.appointment_service import cancel_appointment
from dentacircle.services.recall_service import book_recall, cancel_recall, mark_contacted
from tests.timeline_support import AT_START, NOW, World, book, kinds, later, move, world

pytest_plugins = ["tests.timeline_support"]


def test_completing_a_scaling_visit_records_recall_created(database: str) -> None:
    clinic = world()
    _complete_scaling(clinic, AT_START)
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == ["visit_completed", "recall_created"]


def test_a_later_scaling_visit_records_recall_updated(database: str) -> None:
    clinic = world()
    _complete_scaling(clinic, AT_START)
    _complete_scaling(clinic, later(60))
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == ["visit_completed", "recall_updated"]


def test_mark_contacted_records_recall_contacted(database: str) -> None:
    clinic = world()
    _complete_scaling(clinic, AT_START)
    recall_id = _recall_id(clinic)
    with Session(get_engine()) as session:
        mark_contacted(session, clinic.clinic_id, clinic.actor_id, recall_id, NOW)
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "recall_contacted"


def test_booking_records_recall_booked(database: str) -> None:
    clinic = world()
    _complete_scaling(clinic, AT_START)
    _book(clinic, _recall_id(clinic), later(60))
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == ["visit_booked", "recall_booked"]


def test_completing_the_booked_visit_records_recall_completed(database: str) -> None:
    clinic = world()
    _complete_scaling(clinic, AT_START)
    visit_id = _book(clinic, _recall_id(clinic), later(60))
    move(clinic, visit_id, "arrived")
    move(clinic, visit_id, "in_progress")
    move(clinic, visit_id, "completed")
    written = kinds(clinic.clinic_id, clinic.patient_id)
    assert written[-3:] == ["visit_completed", "recall_completed", "recall_created"]


def test_cancelling_the_booked_visit_records_recall_released(database: str) -> None:
    clinic = world()
    _complete_scaling(clinic, AT_START)
    visit_id = _book(clinic, _recall_id(clinic), later(60))
    with Session(get_engine()) as session:
        cancel_appointment(session, clinic.clinic_id, clinic.actor_id, visit_id, NOW)
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == ["visit_cancelled", "recall_released"]


def test_no_show_on_the_booked_visit_records_recall_released(database: str) -> None:
    clinic = world()
    _complete_scaling(clinic, AT_START)
    visit_id = _book(clinic, _recall_id(clinic), later(60))
    move(clinic, visit_id, "no_show", now=later(60))
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == ["visit_no_show", "recall_released"]


def test_cancel_records_recall_cancelled(database: str) -> None:
    clinic = world()
    _complete_scaling(clinic, AT_START)
    with Session(get_engine()) as session:
        cancel_recall(session, clinic.clinic_id, clinic.actor_id, _recall_id(clinic))
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "recall_cancelled"


def _complete_scaling(clinic: World, start: datetime) -> None:
    visit_id = book(clinic, start, clinic.scaling_id)
    move(clinic, visit_id, "arrived")
    move(clinic, visit_id, "in_progress")
    move(clinic, visit_id, "completed")


def _book(clinic: World, recall_id: UUID, start: datetime) -> UUID:
    with Session(get_engine()) as session:
        visit = book_recall(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            recall_id,
            clinic.clinician_id,
            clinic.scaling_id,
            start,
            NOW,
        )
        session.commit()
        return visit.id


def _recall_id(clinic: World) -> UUID:
    with Session(get_engine()) as session:
        row = session.scalars(
            select(Recall).where(
                Recall.clinic_id == clinic.clinic_id,
                Recall.patient_id == clinic.patient_id,
                Recall.status.in_(("scheduled", "contacted")),
            )
        ).one()
        return row.id
