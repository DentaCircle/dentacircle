"""A care session writes its own audit row and one status row per item."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_session import CareSession
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.appointment_service import book_appointment, change_status
from dentacircle.services.care_service import add_item, change_item_status, create_plan
from dentacircle.services.care_session_service import ItemChangedError, record_session
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_START = datetime(2026, 10, 17, 10, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]
_NAME = "Sample service"
_TITLE = "Sample plan"


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_a_session_records_create_and_one_status_change_per_item(database: str) -> None:
    clinic_id, actor_id, visit_id, first, second = _ready()
    with Session(get_engine()) as session:
        recorded = record_session(
            session,
            clinic_id,
            actor_id,
            visit_id,
            [(first, "started"), (second, "completed")],
        )
        session.commit()
        session_id = recorded.id
    with Session(get_engine()) as session:
        created = AuditRepository(session, clinic_id).list_for_entity("care_session", session_id)
        assert len(created) == 1
        assert created[0].action == "create"
        assert created[0].changed_fields == []
        assert created[0].actor_user_id == actor_id
        for item_id in (first, second):
            events = AuditRepository(session, clinic_id).list_for_entity("care_item", item_id)
            change = next(event for event in events if event.action == "status_change")
            assert change.changed_fields == ["status"]
        stored = _audit_text(session)
        assert _NAME not in stored
        assert _TITLE not in stored
        assert "started" not in stored
        assert "completed" not in stored
        assert "Synthetic Person" not in stored


def test_a_rejected_session_writes_nothing(database: str) -> None:
    clinic_id, actor_id, visit_id, first, second = _ready()
    with Session(get_engine()) as session:
        change_item_status(session, clinic_id, actor_id, second, "completed")
        session.commit()
        before = session.scalar(select(func.count()).select_from(AuditEvent))
    with Session(get_engine()) as session:
        with pytest.raises(ItemChangedError):
            record_session(
                session,
                clinic_id,
                actor_id,
                visit_id,
                [(first, "started"), (second, "completed")],
            )
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == before
        assert session.scalar(select(func.count()).select_from(CareSession)) == 0
        item = session.get(CareItem, first)
        assert item is not None
        assert item.status == "planned"


def test_a_failed_audit_write_saves_nothing(database: str) -> None:
    clinic_id, _actor_id, visit_id, first, _second = _ready()
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            record_session(session, clinic_id, uuid4(), visit_id, [(first, "started")])
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(CareSession)) == 0
        item = session.get(CareItem, first)
        assert item is not None
        assert item.status == "planned"
        assert "started" not in _audit_text(session)


def _audit_text(session: Session) -> str:
    rows = session.execute(text("SELECT * FROM audit_event")).mappings().all()
    return " ".join(str(value) for row in rows for value in row.values())


def _ready() -> tuple[UUID, UUID, UUID, UUID, UUID]:
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
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        first_plan = create_plan(session, clinic.id, actor.id, patient.id, _TITLE)
        second_plan = create_plan(session, clinic.id, actor.id, patient.id, "Second plan")
        first = add_item(session, clinic.id, actor.id, first_plan.id, _NAME)
        second = add_item(session, clinic.id, actor.id, second_plan.id, _NAME)
        session.commit()
        clinic_id, actor_id, patient_id = clinic.id, actor.id, patient.id
        type_id, first_id, second_id = consultation.id, first.id, second.id
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            actor_id,
            type_id,
            _START,
            _START - timedelta(hours=1),
        )
        session.commit()
        visit_id = created.id
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "arrived", _START)
        session.commit()
    return clinic_id, actor_id, visit_id, first_id, second_id
