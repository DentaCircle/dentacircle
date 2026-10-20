"""Each visit step writes its kind. Removing the call fails that test."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.recall import Recall
from dentacircle.services.appointment_service import cancel_appointment, reschedule_appointment
from dentacircle.services.follow_up_service import book_follow_up, create_manual_follow_up
from dentacircle.services.recall_service import book_recall
from tests.timeline_support import AT_START, NOW, World, book, kinds, later, move, world

pytest_plugins = ["tests.timeline_support"]


def test_registration_records_patient_registered(database: str) -> None:
    clinic = world()
    assert kinds(clinic.clinic_id, clinic.patient_id) == ["patient_registered"]


def test_booking_records_visit_booked(database: str) -> None:
    clinic = world()
    book(clinic, AT_START)
    assert kinds(clinic.clinic_id, clinic.patient_id) == ["patient_registered", "visit_booked"]


def test_booking_from_a_follow_up_records_visit_booked(database: str) -> None:
    clinic = world()
    follow_up_id = _manual_follow_up(clinic)
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
    assert "visit_booked" in kinds(clinic.clinic_id, clinic.patient_id)


def test_booking_from_a_recall_records_visit_booked(database: str) -> None:
    clinic = world()
    visit_id = book(clinic, AT_START, clinic.scaling_id)
    move(clinic, visit_id, "arrived")
    move(clinic, visit_id, "in_progress")
    move(clinic, visit_id, "completed")
    recall_id = _open_recall_id(clinic)
    with Session(get_engine()) as session:
        book_recall(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            recall_id,
            clinic.clinician_id,
            clinic.consultation_id,
            later(60),
            NOW,
        )
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id).count("visit_booked") == 2


def test_reschedule_records_visit_rescheduled(database: str) -> None:
    clinic = world()
    visit_id = book(clinic, AT_START)
    with Session(get_engine()) as session:
        reschedule_appointment(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            visit_id,
            later(60),
            None,
            NOW,
        )
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "visit_rescheduled"


def test_cancel_records_visit_cancelled(database: str) -> None:
    clinic = world()
    visit_id = book(clinic, AT_START)
    with Session(get_engine()) as session:
        cancel_appointment(session, clinic.clinic_id, clinic.actor_id, visit_id, NOW)
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "visit_cancelled"


def test_arrived_records_visit_arrived(database: str) -> None:
    clinic = world()
    visit_id = book(clinic, AT_START)
    move(clinic, visit_id, "arrived")
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "visit_arrived"


def test_start_records_visit_started(database: str) -> None:
    clinic = world()
    visit_id = book(clinic, AT_START)
    move(clinic, visit_id, "arrived")
    move(clinic, visit_id, "in_progress")
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "visit_started"


def test_complete_records_visit_completed(database: str) -> None:
    clinic = world()
    visit_id = book(clinic, AT_START)
    move(clinic, visit_id, "arrived")
    move(clinic, visit_id, "in_progress")
    move(clinic, visit_id, "completed")
    assert "visit_completed" in kinds(clinic.clinic_id, clinic.patient_id)


def test_no_show_records_visit_no_show(database: str) -> None:
    clinic = world()
    visit_id = book(clinic, AT_START)
    move(clinic, visit_id, "no_show", now=AT_START)
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "visit_no_show"


def _manual_follow_up(clinic: World) -> UUID:
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


def _open_recall_id(clinic: World) -> UUID:
    with Session(get_engine()) as session:
        row = session.scalars(
            select(Recall).where(
                Recall.clinic_id == clinic.clinic_id,
                Recall.patient_id == clinic.patient_id,
                Recall.status == "scheduled",
            )
        ).one()
        return row.id
