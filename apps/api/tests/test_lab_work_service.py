"""Lab work rules: title, visit ownership, inactive patients, audit names, rollback."""

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.lab_work import LabWorkFieldError
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.lab_work import LabWork
from dentacircle.models.timeline_event import TimelineEvent
from dentacircle.services.appointment_service import book_appointment
from dentacircle.services.lab_work_service import (
    InvalidLabStatusError,
    LabWorkNotFoundError,
    LabWorkPatientInactiveError,
    LabWorkView,
    change_lab_status,
    create_lab_work,
    get_lab_work,
    list_clinic_lab_work,
    list_patient_lab_work,
)
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from dentacircle.services.timeline_service import LabWorkSubject, list_timeline
from tests.timeline_support import AT_START, NOW, World, book, world

pytest_plugins = ["tests.timeline_support"]

_TODAY = date(2026, 10, 12)
_TITLE = "Crown"


def test_a_new_item_is_pending_and_writes_audit_and_timeline(database: str) -> None:
    clinic = world()
    created = _create(clinic, f"  {_TITLE}  ", expected_on=_TODAY)
    assert created.status == "pending"
    assert created.title == _TITLE
    assert created.expected_on == _TODAY
    assert created.overdue is False
    assert created.appointment is None
    assert created.patient.id == clinic.patient_id
    assert created.created_by.name == "Sample Desk"
    assert created.created_at.utcoffset() is not None
    assert created.created_at.utcoffset().total_seconds() == 5.5 * 3600  # type: ignore[union-attr]
    events = _audits("lab_work")
    assert len(events) == 1
    assert events[0].action == "create"
    assert events[0].changed_fields == []
    assert events[0].entity_id == created.id
    assert _TITLE not in events[0].changed_fields
    with Session(get_engine()) as session:
        found = list_timeline(session, clinic.clinic_id, clinic.patient_id, 1, 20)
    lab_steps = [item for item in found.items if item.kind == "lab_work_created"]
    assert len(lab_steps) == 1
    assert isinstance(lab_steps[0].subject, LabWorkSubject)
    assert lab_steps[0].subject.lab_work_id == created.id
    assert lab_steps[0].subject.title == _TITLE
    with Session(get_engine()) as session:
        row = session.get(TimelineEvent, lab_steps[0].id)
        assert row is not None
        assert row.lab_work_id == created.id
        assert row.appointment_id is None


def test_a_related_visit_must_belong_to_this_patient(database: str) -> None:
    clinic = world()
    visit_id = book(clinic, AT_START)
    created = _create(clinic, _TITLE, appointment_id=visit_id)
    assert created.appointment is not None
    assert created.appointment.id == visit_id
    assert created.appointment.type_name == "Consultation"
    assert created.appointment.starts_at.isoformat().endswith("+05:30")

    other_id = _other_patient(clinic)
    with Session(get_engine()) as session:
        other_visit = book_appointment(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            other_id,
            clinic.clinician_id,
            clinic.consultation_id,
            AT_START + timedelta(hours=2),
            NOW,
        )
        session.commit()
        other_visit_id = other_visit.id
    with pytest.raises(LabWorkNotFoundError):
        _create(clinic, _TITLE, appointment_id=other_visit_id)
    with pytest.raises(LabWorkNotFoundError):
        _create(clinic, _TITLE, appointment_id=uuid4())
    assert _count(LabWork) == 1


def test_a_bad_title_or_date_is_refused_before_the_patient_is_looked_up(database: str) -> None:
    clinic = world()
    missing = uuid4()
    with pytest.raises(LabWorkFieldError) as blank:
        _create(clinic, "  ", patient_id=missing)
    assert blank.value.code == "string_too_short"
    with pytest.raises(LabWorkFieldError) as early:
        _create(clinic, _TITLE, expected_on=_TODAY - timedelta(days=1), patient_id=missing)
    assert early.value.code == "before_today"
    with pytest.raises(LabWorkFieldError) as late:
        _create(clinic, _TITLE, expected_on=_TODAY + timedelta(days=366), patient_id=missing)
    assert late.value.code == "beyond_horizon"
    assert _count(LabWork) == 0
    with pytest.raises(LabWorkNotFoundError):
        _create(clinic, _TITLE, patient_id=missing)


def test_an_inactive_patient_cannot_gain_lab_work_but_can_still_be_listed(
    database: str,
) -> None:
    clinic = world()
    created = _create(clinic, _TITLE)
    _deactivate(clinic)
    with pytest.raises(LabWorkPatientInactiveError):
        _create(clinic, "Bridge")
    assert _count(LabWork) == 1
    with Session(get_engine()) as session:
        page = list_patient_lab_work(session, clinic.clinic_id, clinic.patient_id, 1, 20, NOW)
    assert [item.id for item in page.items] == [created.id]


def test_a_failed_audit_or_timeline_write_leaves_no_row(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic = world()

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("write failed")

    monkeypatch.setattr("dentacircle.services.lab_work_service.record", fail)
    with pytest.raises(RuntimeError):
        _create(clinic, _TITLE)
    assert _count(LabWork) == 0
    assert _audits("lab_work") == []

    monkeypatch.setattr("dentacircle.services.lab_work_service.record", record_ok)
    monkeypatch.setattr("dentacircle.services.lab_work_service.record_timeline", fail)
    with pytest.raises(RuntimeError):
        _create(clinic, _TITLE)
    assert _count(LabWork) == 0
    assert _audits("lab_work") == []


def test_a_status_move_records_the_field_name_only(database: str) -> None:
    clinic = world()
    created = _create(clinic, _TITLE)
    with Session(get_engine()) as session:
        moved = change_lab_status(
            session, clinic.clinic_id, clinic.actor_id, created.id, "cancelled", NOW
        )
        session.commit()
    assert moved.status == "cancelled"
    events = [row for row in _audits("lab_work") if row.action == "status_change"]
    assert len(events) == 1
    assert events[0].changed_fields == ["status"]
    assert "cancelled" not in events[0].changed_fields
    with pytest.raises(InvalidLabStatusError):
        _move(clinic, created.id, "ready")
    with pytest.raises(InvalidLabStatusError):
        _move(clinic, created.id, "pending")
    with pytest.raises(InvalidLabStatusError):
        _move(clinic, created.id, "collected")


def test_pending_cannot_skip_to_collected(database: str) -> None:
    clinic = world()
    created = _create(clinic, _TITLE)
    with pytest.raises(InvalidLabStatusError):
        _move(clinic, created.id, "collected")
    with Session(get_engine()) as session:
        row = session.get(LabWork, created.id)
        assert row is not None
        assert row.status == "pending"


def test_the_patient_list_is_newest_first_and_another_clinic_is_missing(database: str) -> None:
    clinic = world()
    first = _create(clinic, "Crown")
    second = _create(clinic, "Bridge")
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE lab_work SET created_at = created_at - interval '1 hour' WHERE id = :id"),
            {"id": first.id},
        )
        session.commit()
        page = list_patient_lab_work(session, clinic.clinic_id, clinic.patient_id, 1, 20, NOW)
        found = get_lab_work(session, clinic.clinic_id, second.id, NOW)
    assert [item.id for item in page.items] == [second.id, first.id]
    assert found.title == "Bridge"
    other_clinic, other_user = _other_clinic()
    with pytest.raises(LabWorkNotFoundError):
        with Session(get_engine()) as session:
            get_lab_work(session, other_clinic, second.id, NOW)
    with pytest.raises(LabWorkNotFoundError):
        _create(clinic, _TITLE, clinic_id=other_clinic, actor_id=other_user)


def test_the_clinic_list_orders_empty_dates_last_and_calculates_overdue(database: str) -> None:
    clinic = world()
    dated = _create(clinic, "Crown", expected_on=_TODAY)
    undated = _create(clinic, "Bridge")
    later = _create(clinic, "Denture", expected_on=_TODAY + timedelta(days=2))
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE lab_work SET created_at = created_at - interval '2 hours' WHERE id = :id"),
            {"id": dated.id},
        )
        ready = change_lab_status(
            session, clinic.clinic_id, clinic.actor_id, later.id, "ready", NOW
        )
        session.commit()
        page = list_clinic_lab_work(session, clinic.clinic_id, "open", 1, 20, NOW)
    by_title = {item.title: item for item in page.items}
    assert [item.title for item in page.items] == ["Crown", "Denture", "Bridge"]
    assert by_title["Crown"].overdue is False
    assert by_title["Denture"].overdue is False
    assert ready.status == "ready"
    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE lab_work SET expected_on = :day WHERE id = :id"),
            {"day": _TODAY - timedelta(days=1), "id": dated.id},
        )
        session.commit()
        overdue = list_clinic_lab_work(session, clinic.clinic_id, "open", 1, 20, NOW)
    flags = {item.title: item.overdue for item in overdue.items}
    assert flags["Crown"] is True
    assert flags["Denture"] is False
    assert undated.expected_on is None


def record_ok(*_args: object, **_kwargs: object) -> None:
    from dentacircle.services.audit_service import record

    record(*_args, **_kwargs)  # type: ignore[arg-type]


def _create(
    clinic: World,
    title: str,
    *,
    expected_on: date | None = None,
    appointment_id: UUID | None = None,
    patient_id: UUID | None = None,
    clinic_id: UUID | None = None,
    actor_id: UUID | None = None,
) -> LabWorkView:
    with Session(get_engine()) as session:
        created = create_lab_work(
            session,
            clinic.clinic_id if clinic_id is None else clinic_id,
            clinic.actor_id if actor_id is None else actor_id,
            clinic.patient_id if patient_id is None else patient_id,
            title,
            expected_on,
            appointment_id,
            NOW,
        )
        session.commit()
        return created


def _move(clinic: World, lab_work_id: UUID, status: str) -> LabWorkView:
    with Session(get_engine()) as session:
        moved = change_lab_status(
            session, clinic.clinic_id, clinic.actor_id, lab_work_id, status, NOW
        )
        session.commit()
        return moved


def _deactivate(clinic: World) -> None:
    with Session(get_engine()) as session:
        set_patient_status(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "inactive"
        )
        session.commit()


def _other_patient(clinic: World) -> UUID:
    with Session(get_engine()) as session:
        patient = register_patient(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            "Sample Bea",
            "9000000002",
            None,
            occurred_at=NOW,
        )
        session.commit()
        return patient.id


def _other_clinic() -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Another Synthetic Clinic")
        user = create_user(
            session,
            other.id,
            "other@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        session.commit()
        return other.id, user.id


def _audits(entity_type: str) -> list[AuditEvent]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == entity_type)
                .order_by(AuditEvent.occurred_at)
            )
        )


def _count(model: type[LabWork]) -> int:
    with Session(get_engine()) as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)
