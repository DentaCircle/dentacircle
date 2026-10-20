"""Each care step writes its kind. Removing the call fails that test."""

from uuid import UUID

from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.services.care_service import add_item, change_item_status, create_plan
from dentacircle.services.care_session_service import record_session
from tests.timeline_support import AT_START, NOW, World, book, kinds, move, world

pytest_plugins = ["tests.timeline_support"]


def test_adding_an_item_records_care_item_added(database: str) -> None:
    clinic = world()
    _add_item(clinic, "Scaling")
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "care_item_added"


def test_starting_an_item_records_care_item_started(database: str) -> None:
    clinic = world()
    item_id = _add_item(clinic, "Scaling")
    _move_item(clinic, item_id, "started")
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "care_item_started"


def test_completing_an_item_records_care_item_completed(database: str) -> None:
    clinic = world()
    item_id = _add_item(clinic, "Scaling")
    _move_item(clinic, item_id, "completed")
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "care_item_completed"


def test_cancelling_an_item_records_care_item_cancelled(database: str) -> None:
    clinic = world()
    item_id = _add_item(clinic, "Scaling")
    _move_item(clinic, item_id, "cancelled")
    assert kinds(clinic.clinic_id, clinic.patient_id)[-1] == "care_item_cancelled"


def test_a_session_records_the_item_move_and_the_session(database: str) -> None:
    clinic = world()
    item_id = _add_item(clinic, "Scaling")
    visit_id = book(clinic, AT_START)
    move(clinic, visit_id, "arrived")
    with Session(get_engine()) as session:
        record_session(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            visit_id,
            [(item_id, "completed")],
            occurred_at=NOW,
        )
        session.commit()
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == [
        "care_item_completed",
        "care_session_recorded",
    ]


def _add_item(clinic: World, name: str) -> UUID:
    with Session(get_engine()) as session:
        plan = create_plan(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "Sample plan"
        )
        item = add_item(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            plan.id,
            name,
            occurred_at=NOW,
        )
        session.commit()
        return item.id


def _move_item(clinic: World, item_id: UUID, target: str) -> None:
    with Session(get_engine()) as session:
        change_item_status(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            item_id,
            target,
            occurred_at=NOW,
        )
        session.commit()
