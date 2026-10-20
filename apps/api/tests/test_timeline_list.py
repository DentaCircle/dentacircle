"""The timeline list is newest first, live, and scoped to the clinic."""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.models.app_user import AppUser
from dentacircle.models.audit_event import AuditEvent
from dentacircle.services.care_service import add_item, create_plan, rename_item
from dentacircle.services.patient_service import (
    PatientNotFoundError,
    register_patient,
    set_patient_status,
)
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from dentacircle.services.timeline_service import (
    CareItemSubject,
    FollowUpSubject,
    VisitSubject,
    list_timeline,
)
from tests.timeline_support import AT_START, NOW, book, kinds, later, move, world

pytest_plugins = ["tests.timeline_support"]


def test_newest_first_and_paging(database: str) -> None:
    clinic = world()
    book(clinic, AT_START)
    book(clinic, later(60))
    with Session(get_engine()) as session:
        page = list_timeline(session, clinic.clinic_id, clinic.patient_id, 1, 1)
        second = list_timeline(session, clinic.clinic_id, clinic.patient_id, 2, 1)
    assert page.total == 3
    assert page.page == 1
    assert page.page_size == 1
    assert [item.kind for item in page.items] == ["visit_booked"]
    assert [item.kind for item in second.items] == ["visit_booked"]
    assert page.items[0].id != second.items[0].id
    assert page.items[0].occurred_at >= second.items[0].occurred_at


def test_one_completion_lists_the_new_follow_up_before_the_visit(database: str) -> None:
    clinic = world()
    with Session(get_engine()) as session:
        plan = create_plan(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "Sample plan"
        )
        add_item(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            plan.id,
            "Root canal",
            occurred_at=NOW,
        )
        session.commit()
    visit_id = book(clinic, AT_START)
    move(clinic, visit_id, "arrived")
    move(clinic, visit_id, "in_progress")
    move(clinic, visit_id, "completed")
    assert kinds(clinic.clinic_id, clinic.patient_id)[-2:] == [
        "visit_completed",
        "follow_up_created",
    ]
    with Session(get_engine()) as session:
        page = list_timeline(session, clinic.clinic_id, clinic.patient_id, 1, 20)
    assert [item.kind for item in page.items][:2] == ["follow_up_created", "visit_completed"]
    follow_up = page.items[0].subject
    visit = page.items[1].subject
    assert isinstance(follow_up, FollowUpSubject)
    assert isinstance(visit, VisitSubject)
    assert visit.type_name == "Consultation"
    assert visit.clinician_name == "Sample Clinician"
    assert follow_up.due_on == date(2026, 10, 19)


def test_a_renamed_item_shows_its_current_name(database: str) -> None:
    clinic = world()
    with Session(get_engine()) as session:
        plan = create_plan(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "Sample plan"
        )
        item = add_item(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            plan.id,
            "Scaling",
            occurred_at=NOW,
        )
        session.commit()
        item_id = item.id
    with Session(get_engine()) as session:
        rename_item(session, clinic.clinic_id, clinic.actor_id, item_id, "Scale and polish")
        session.commit()
    with Session(get_engine()) as session:
        page = list_timeline(session, clinic.clinic_id, clinic.patient_id, 1, 20)
    added = next(item for item in page.items if item.kind == "care_item_added")
    assert isinstance(added.subject, CareItemSubject)
    assert added.subject.name == "Scale and polish"


def test_a_deactivated_actor_still_resolves(database: str) -> None:
    clinic = world()
    with Session(get_engine()) as session:
        user = session.get(AppUser, clinic.actor_id)
        assert user is not None
        user.is_active = False
        session.commit()
    with Session(get_engine()) as session:
        page = list_timeline(session, clinic.clinic_id, clinic.patient_id, 1, 20)
    assert page.items[0].actor.name == "Sample Desk"
    assert page.items[0].actor.id == clinic.actor_id


def test_an_inactive_patient_can_be_read_and_reading_writes_no_audit(database: str) -> None:
    clinic = world()
    with Session(get_engine()) as session:
        set_patient_status(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "inactive"
        )
        session.commit()
        before = session.scalar(select(func.count()).select_from(AuditEvent))
        page = list_timeline(session, clinic.clinic_id, clinic.patient_id, 1, 20)
        session.commit()
        after = session.scalar(select(func.count()).select_from(AuditEvent))
    assert page.total == 1
    assert page.items[0].kind == "patient_registered"
    assert page.items[0].subject is None
    assert after == before


def test_another_clinic_patient_is_missing(database: str) -> None:
    clinic = world()
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        actor = create_user(
            session,
            other.id,
            "other@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, other.id, actor.id, "Sample Bea", "9000000002", None)
        session.commit()
        other_patient = patient.id
    with Session(get_engine()) as session:
        page = list_timeline(session, clinic.clinic_id, clinic.patient_id, 1, 20)
        assert page.total == 1
        with pytest.raises(PatientNotFoundError):
            list_timeline(session, clinic.clinic_id, other_patient, 1, 20)
