"""A successful registration writes one audit event, and a failed one writes nothing."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.patient import Patient
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.patient_service import (
    PatientChanges,
    edit_patient,
    register_patient,
    set_patient_status,
)
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_NAME = "Sample Ada"
_PHONE = "9000000001"
_BORN = date(1990, 4, 5)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_register_writes_one_event_without_patient_values(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    with Session(get_engine()) as session:
        created = register_patient(
            session, clinic_id, actor_id, f"  {_NAME}  ", f" {_PHONE} ", _BORN
        )
        session.commit()
        patient_id = created.id

    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("patient", patient_id)
        assert len(events) == 1
        event = events[0]
        assert event.clinic_id == clinic_id
        assert event.actor_user_id == actor_id
        assert event.entity_type == "patient"
        assert event.entity_id == patient_id
        assert event.action == "create"
        assert event.changed_fields == []
        assert event.occurred_at is not None
        row = session.execute(text("SELECT * FROM audit_event")).mappings().one()
        stored = " ".join(str(value) for value in row.values())
        assert _NAME not in stored
        assert _PHONE not in stored
        assert "1990-04-05" not in stored
        assert "full_name" not in row
        assert "phone" not in row
        assert "date_of_birth" not in row


def test_an_edit_records_field_names_and_not_values(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    patient_id = _register(clinic_id, actor_id)
    new_phone = "9000000002"
    with Session(get_engine()) as session:
        edit_patient(
            session,
            clinic_id,
            actor_id,
            patient_id,
            PatientChanges(fields=frozenset({"phone"}), phone=new_phone),
        )
        session.commit()
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("patient", patient_id)
        update = next(event for event in events if event.action == "update")
        assert update.changed_fields == ["phone"]
        assert update.entity_type == "patient"
        assert update.actor_user_id == actor_id
        stored = _audit_text(session)
        assert new_phone not in stored
        assert _PHONE not in stored
        assert _NAME not in stored
        assert "1990-04-05" not in stored


def test_a_status_change_records_the_field_and_not_the_direction(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    patient_id = _register(clinic_id, actor_id)
    with Session(get_engine()) as session:
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("patient", patient_id)
        change = next(event for event in events if event.action == "status_change")
        assert change.changed_fields == ["status"]
        stored = _audit_text(session)
        assert "inactive" not in stored
        assert "active" not in stored


def test_a_failed_audit_write_does_not_save_the_edit(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    patient_id = _register(clinic_id, actor_id)
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            edit_patient(
                session,
                clinic_id,
                uuid4(),
                patient_id,
                PatientChanges(fields=frozenset({"phone"}), phone="9000000002"),
            )
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            set_patient_status(session, clinic_id, uuid4(), patient_id, "inactive")
    with Session(get_engine()) as session:
        row = session.get(Patient, patient_id)
        assert row is not None
        assert row.phone == _PHONE
        assert row.status == "active"
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_a_failed_audit_write_does_not_save_the_patient(database: str) -> None:
    clinic_id, _actor_id = _clinic_and_actor()
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            register_patient(session, clinic_id, uuid4(), _NAME, _PHONE, _BORN)
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Patient)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_audit_repository_has_no_update_or_delete() -> None:
    public = {
        name
        for name, value in vars(AuditRepository).items()
        if callable(value) and not name.startswith("_")
    }
    assert public == {"add", "list_for_entity"}


def _register(clinic_id: UUID, actor_id: UUID) -> UUID:
    with Session(get_engine()) as session:
        created = register_patient(session, clinic_id, actor_id, _NAME, _PHONE, _BORN)
        session.commit()
        return created.id


def _audit_text(session: Session) -> str:
    rows = session.execute(text("SELECT * FROM audit_event")).mappings().all()
    return " ".join(str(value) for row in rows for value in row.values())


def _clinic_and_actor() -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "a@x.test",
            "Synthetic Person",
            "synthetic-password-marker",
            ["receptionist"],
        )
        session.commit()
        return clinic.id, actor.id
