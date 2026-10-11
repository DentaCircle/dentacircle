"""Edit and status changes. Audit contents are checked in test_patient_audit.py."""

from datetime import date
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.patient import PatientFieldError, changed_field_names
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.patient import Patient
from dentacircle.services.patient_service import (
    PatientChanges,
    PatientNotFoundError,
    edit_patient,
    register_patient,
    set_patient_status,
)
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_NAME = "Sample Ada"
_PHONE = "9000000001"
_BORN = date(1990, 4, 5)


def test_changed_field_names_lists_only_allowed_names_that_differ() -> None:
    before = {
        "full_name": _NAME,
        "phone": _PHONE,
        "phone_digits": _PHONE,
        "date_of_birth": _BORN,
        "status": "active",
    }
    after = {
        "full_name": _NAME,
        "phone": "9000000002",
        "phone_digits": "9000000002",
        "date_of_birth": None,
        "status": "inactive",
    }
    assert changed_field_names(before, after) == ["phone", "date_of_birth", "status"]
    assert changed_field_names({"status": "active"}, {"status": "active"}) == []
    assert "phone_digits" not in changed_field_names(before, after)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_edit_updates_only_the_sent_fields_and_recalculates_digits(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    patient_id = _register(clinic_id, actor_id, _BORN)
    with Session(get_engine()) as session:
        updated = edit_patient(
            session,
            clinic_id,
            actor_id,
            patient_id,
            PatientChanges(fields=frozenset({"phone"}), phone=" +91 90000 00002 "),
        )
        session.commit()
    assert updated.full_name == _NAME
    assert updated.date_of_birth == _BORN
    assert updated.phone == "+91 90000 00002"
    assert updated.patient_number == 1
    assert updated.status == "active"
    with Session(get_engine()) as session:
        row = session.get(Patient, patient_id)
        assert row is not None
        assert row.phone_digits == "919000000002"


def test_clearing_the_date_of_birth_stores_null(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    patient_id = _register(clinic_id, actor_id, _BORN)
    with Session(get_engine()) as session:
        updated = edit_patient(
            session,
            clinic_id,
            actor_id,
            patient_id,
            PatientChanges(fields=frozenset({"date_of_birth"}), date_of_birth=None),
        )
        session.commit()
    assert updated.date_of_birth is None


def test_a_rejected_edit_changes_nothing(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    patient_id = _register(clinic_id, actor_id, _BORN)
    with Session(get_engine()) as session:
        with pytest.raises(PatientFieldError):
            edit_patient(
                session,
                clinic_id,
                actor_id,
                patient_id,
                PatientChanges(fields=frozenset({"full_name", "date_of_birth"}), full_name=None),
            )
        with pytest.raises(PatientFieldError):
            edit_patient(
                session,
                clinic_id,
                actor_id,
                patient_id,
                PatientChanges(
                    fields=frozenset({"date_of_birth"}), date_of_birth=date(1899, 12, 31)
                ),
            )
    with Session(get_engine()) as session:
        row = session.get(Patient, patient_id)
        assert row is not None
        assert row.full_name == _NAME
        assert row.date_of_birth == _BORN
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_an_edit_that_changes_nothing_writes_no_audit_event(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    patient_id = _register(clinic_id, actor_id, _BORN)
    with Session(get_engine()) as session:
        updated = edit_patient(
            session,
            clinic_id,
            actor_id,
            patient_id,
            PatientChanges(
                fields=frozenset({"full_name", "phone", "date_of_birth"}),
                full_name=f"  {_NAME}  ",
                phone=f" {_PHONE} ",
                date_of_birth=_BORN,
            ),
        )
        session.commit()
    assert updated.full_name == _NAME
    assert updated.phone == _PHONE
    with Session(get_engine()) as session:
        actions = session.scalars(select(AuditEvent.action)).all()
    assert actions == ["create"]


def test_status_change_keeps_the_row_and_a_repeat_writes_no_audit_event(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    patient_id = _register(clinic_id, actor_id, _BORN)
    with Session(get_engine()) as session:
        inactive = set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
    assert inactive.status == "inactive"
    assert inactive.patient_number == 1
    assert inactive.full_name == _NAME
    assert inactive.phone == _PHONE
    assert inactive.date_of_birth == _BORN
    with Session(get_engine()) as session:
        again = set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
        assert again.status == "inactive"
        assert session.get(Patient, patient_id) is not None
        actions = session.scalars(select(AuditEvent.action).order_by(AuditEvent.occurred_at)).all()
    assert actions == ["create", "status_change"]


def test_an_unknown_status_is_rejected(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    patient_id = _register(clinic_id, actor_id, None)
    with Session(get_engine()) as session:
        with pytest.raises(PatientFieldError) as caught:
            set_patient_status(session, clinic_id, actor_id, patient_id, "gone")
    assert caught.value.field == "status"
    with Session(get_engine()) as session:
        row = session.get(Patient, patient_id)
        assert row is not None
        assert row.status == "active"


def test_another_clinic_cannot_load_the_patient(database: str) -> None:
    clinic_id, actor_id = _clinic_and_actor()
    patient_id = _register(clinic_id, actor_id, None)
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        session.commit()
        other_id = other.id
    with Session(get_engine()) as session:
        with pytest.raises(PatientNotFoundError):
            edit_patient(
                session,
                other_id,
                actor_id,
                patient_id,
                PatientChanges(fields=frozenset({"phone"}), phone="9000000002"),
            )
        with pytest.raises(PatientNotFoundError):
            set_patient_status(session, other_id, actor_id, patient_id, "inactive")


def _register(clinic_id: UUID, actor_id: UUID, born: date | None) -> UUID:
    with Session(get_engine()) as session:
        created = register_patient(session, clinic_id, actor_id, _NAME, _PHONE, born)
        session.commit()
        return created.id


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
