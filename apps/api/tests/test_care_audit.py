"""A successful care write records one audit event, and a failed one records nothing."""

from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_plan import CarePlan
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.care_service import (
    InvalidStatusError,
    PatientInactiveError,
    add_item,
    change_item_status,
    create_plan,
    rename_item,
    rename_plan,
)
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_TITLE = "Sample plan"
_NAME = "Sample service"


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_create_records_the_action_and_not_the_title(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    with Session(get_engine()) as session:
        created = create_plan(session, clinic_id, actor_id, patient_id, _TITLE)
        session.commit()
        plan_id = created.id
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("care_plan", plan_id)
        assert len(events) == 1
        event = events[0]
        assert event.action == "create"
        assert event.changed_fields == []
        assert event.actor_user_id == actor_id
        assert event.entity_type == "care_plan"
        assert _TITLE not in _audit_text(session)


def test_a_rename_records_the_field_name_and_not_the_value(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    plan_id, item_id = _plan_and_item(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        rename_plan(session, clinic_id, actor_id, plan_id, "Other plan")
        rename_item(session, clinic_id, actor_id, item_id, "Other service")
        session.commit()
    with Session(get_engine()) as session:
        plan_events = AuditRepository(session, clinic_id).list_for_entity("care_plan", plan_id)
        item_events = AuditRepository(session, clinic_id).list_for_entity("care_item", item_id)
        assert next(event.changed_fields for event in plan_events if event.action == "update") == [
            "title"
        ]
        assert next(event.changed_fields for event in item_events if event.action == "update") == [
            "name"
        ]
        stored = _audit_text(session)
        assert "Other plan" not in stored
        assert "Other service" not in stored
        assert _TITLE not in stored
        assert _NAME not in stored


def test_a_status_change_records_the_field_and_not_the_value(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    _plan_id, item_id = _plan_and_item(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        change_item_status(session, clinic_id, actor_id, item_id, "started")
        session.commit()
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("care_item", item_id)
        change = next(event for event in events if event.action == "status_change")
        assert change.changed_fields == ["status"]
        stored = _audit_text(session)
        assert "started" not in stored
        assert "planned" not in stored


def test_a_rejected_request_writes_nothing(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    plan_id, item_id = _plan_and_item(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        change_item_status(session, clinic_id, actor_id, item_id, "completed")
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
        before = session.scalar(select(func.count()).select_from(AuditEvent))
    with Session(get_engine()) as session:
        with pytest.raises(InvalidStatusError):
            change_item_status(session, clinic_id, actor_id, item_id, "started")
        with pytest.raises(InvalidStatusError):
            rename_item(session, clinic_id, actor_id, item_id, "Nope")
        with pytest.raises(PatientInactiveError):
            add_item(session, clinic_id, actor_id, plan_id, "Nope")
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == before
        item = session.get(CareItem, item_id)
        assert item is not None
        assert item.name == _NAME
        assert item.status == "completed"


def test_a_failed_audit_write_saves_nothing(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    plan_id, item_id = _plan_and_item(clinic_id, actor_id, patient_id)
    stranger = uuid4()
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            create_plan(session, clinic_id, stranger, patient_id, "Lost")
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            add_item(session, clinic_id, stranger, plan_id, "Lost")
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            rename_plan(session, clinic_id, stranger, plan_id, "Lost")
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            rename_item(session, clinic_id, stranger, item_id, "Lost")
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            change_item_status(session, clinic_id, stranger, item_id, "started")
    with Session(get_engine()) as session:
        plans = session.scalars(select(CarePlan).where(CarePlan.patient_id == patient_id)).all()
        assert [plan.title for plan in plans] == [_TITLE]
        item = session.get(CareItem, item_id)
        assert item is not None
        assert item.name == _NAME
        assert item.status == "planned"
        stored = _audit_text(session)
        assert "Lost" not in stored
        assert "started" not in stored


def _audit_text(session: Session) -> str:
    rows = session.execute(text("SELECT * FROM audit_event")).mappings().all()
    return " ".join(str(value) for row in rows for value in row.values())


def _world() -> tuple[UUID, UUID, UUID]:
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
        session.commit()
        return clinic.id, actor.id, patient.id


def _plan_and_item(clinic_id: UUID, actor_id: UUID, patient_id: UUID) -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        plan = create_plan(session, clinic_id, actor_id, patient_id, _TITLE)
        item = add_item(session, clinic_id, actor_id, plan.id, _NAME)
        session.commit()
        return plan.id, item.id
