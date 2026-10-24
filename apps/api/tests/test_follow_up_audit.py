"""Follow-up create and update write an audit row, and a failed write saves nothing."""

from datetime import datetime, timedelta
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
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.follow_up import FollowUp
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.appointment_service import book_appointment, change_status
from dentacircle.services.audit_service import record as record_audit
from dentacircle.services.care_service import add_item, create_plan
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_START = datetime(2026, 10, 17, 10, 0, tzinfo=_ZONE)
_LATER = datetime(2026, 10, 17, 11, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]
_NAME = "Sample Ada"
_TITLE = "Sample plan"


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_create_and_update_record_the_actor_and_not_the_values(database: str) -> None:
    clinic_id, actor_id, other_id, patient_id, type_id = _world()
    _item(clinic_id, actor_id, patient_id)
    first = _visit(clinic_id, actor_id, patient_id, type_id, _START)
    second = _visit(clinic_id, actor_id, patient_id, type_id, _LATER)
    _advance(clinic_id, actor_id, first, _START)
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, first, "completed", _START)
        session.commit()
    follow_up_id = _only_id(patient_id)
    with Session(get_engine()) as session:
        created = AuditRepository(session, clinic_id).list_for_entity("follow_up", follow_up_id)
        visit_events = AuditRepository(session, clinic_id).list_for_entity("appointment", first)
        assert [(event.action, event.changed_fields) for event in created] == [("create", [])]
        assert created[0].actor_user_id == actor_id
        assert created[0].entity_type == "follow_up"
        assert any(event.action == "status_change" for event in visit_events)
        follow_up = session.get(FollowUp, follow_up_id)
        assert follow_up is not None
        stored = _audit_sensitive_text(session)
        assert _NAME not in stored
        assert _TITLE not in stored
        assert follow_up.due_on.isoformat() not in stored
    _advance(clinic_id, other_id, second, _LATER)
    with Session(get_engine()) as session:
        change_status(session, clinic_id, other_id, _ROLES, second, "completed", _LATER)
        session.commit()
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("follow_up", follow_up_id)
        updated = next(event for event in events if event.action == "update")
        assert updated.changed_fields == ["appointment_id"]
        assert updated.actor_user_id == other_id
        assert follow_up.due_on.isoformat() not in _audit_sensitive_text(session)
        row = session.get(FollowUp, follow_up_id)
        assert row is not None
        assert row.appointment_id == second


def test_a_failed_follow_up_audit_saves_nothing(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic_id, actor_id, _other_id, patient_id, type_id = _world()
    _item(clinic_id, actor_id, patient_id)
    visit_id = _visit(clinic_id, actor_id, patient_id, type_id, _START)
    _advance(clinic_id, actor_id, visit_id, _START)
    before = _audit_count()

    def fail_follow_up(
        session: Session,
        clinic_id: UUID,
        actor_user_id: UUID,
        entity_type: str,
        entity_id: UUID,
        action: str,
        changed_fields: list[str] | None = None,
    ) -> None:
        if entity_type == "follow_up":
            raise IntegrityError("INSERT", {}, Exception("forced"))
        record_audit(
            session,
            clinic_id,
            actor_user_id,
            entity_type,
            entity_id,
            action,
            changed_fields,
        )

    monkeypatch.setattr("dentacircle.services.follow_up_service.record", fail_follow_up)
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", _START)
    with Session(get_engine()) as session:
        visit = session.get(Appointment, visit_id)
        assert visit is not None
        assert visit.status == "in_progress"
        assert session.scalar(select(func.count()).select_from(FollowUp)) == 0
    assert _audit_count() == before


def _advance(clinic_id: UUID, actor_id: UUID, visit_id: UUID, now: datetime) -> None:
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "arrived", now)
        change_status(session, clinic_id, actor_id, _ROLES, visit_id, "in_progress", now)
        session.commit()


def _visit(
    clinic_id: UUID, actor_id: UUID, patient_id: UUID, type_id: UUID, start: datetime
) -> UUID:
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
        return created.id


def _item(clinic_id: UUID, actor_id: UUID, patient_id: UUID) -> None:
    with Session(get_engine()) as session:
        plan = create_plan(session, clinic_id, actor_id, patient_id, _TITLE)
        add_item(session, clinic_id, actor_id, plan.id, "Sample service")
        session.commit()


def _world() -> tuple[UUID, UUID, UUID, UUID, UUID]:
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
        other = create_user(
            session,
            clinic.id,
            "c@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, _NAME, "9000000001", None)
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        return clinic.id, actor.id, other.id, patient.id, consultation.id


def _only_id(patient_id: UUID) -> UUID:
    with Session(get_engine()) as session:
        row = session.scalars(select(FollowUp).where(FollowUp.patient_id == patient_id)).one()
        return row.id


def _audit_sensitive_text(session: Session) -> str:
    """Action and field names only. Timestamps and ids are not checked for PHI."""
    rows = session.execute(
        text("SELECT entity_type, action, changed_fields FROM audit_event")
    ).mappings().all()
    parts: list[str] = []
    for row in rows:
        parts.append(str(row["entity_type"]))
        parts.append(str(row["action"]))
        fields = row["changed_fields"]
        if fields is not None:
            parts.extend(str(name) for name in fields)
    return " ".join(parts)


def _audit_count() -> int:
    with Session(get_engine()) as session:
        found = session.scalar(select(func.count()).select_from(AuditEvent))
    return int(found or 0)
