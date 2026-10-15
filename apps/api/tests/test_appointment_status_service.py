"""Status moves, the clock, audit, and an inactive patient. The pair table is written here."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.appointment import AppointmentFieldError
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.clinic import Clinic
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.repositories.audit_repository import AuditRepository
from dentacircle.services.appointment_service import (
    InvalidStatusError,
    SlotTakenError,
    book_appointment,
    change_status,
    find_availability,
)
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_LONDON = ZoneInfo("Europe/London")
_BOOK_NOW = datetime(2026, 10, 14, 8, 0, tzinfo=_ZONE)
_START = datetime(2026, 10, 15, 10, 0, tzinfo=_ZONE)
_NOW = _START
_ROLES = ["clinician"]
_NAME = "Sample Ada"
_STATUSES = ("scheduled", "arrived", "in_progress", "completed", "cancelled", "no_show")
# Written here on purpose. The test must not read STATUS_TRANSITIONS.
_ALLOWED = {
    ("scheduled", "arrived"),
    ("scheduled", "no_show"),
    ("arrived", "in_progress"),
    ("in_progress", "completed"),
}
_EXPECTED = {
    (source, target): "ok" if (source, target) in _ALLOWED else "invalid"
    for source in _STATUSES
    for target in _STATUSES
}


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_every_status_pair_matches_the_written_table(database: str) -> None:
    assert len(_EXPECTED) == 36
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id)
    for source, target in _EXPECTED:
        _set_status(appointment_id, source)
        with Session(get_engine()) as session:
            before = _appointment_audits(session)
            if _EXPECTED[(source, target)] == "ok":
                changed = change_status(
                    session, clinic_id, actor_id, _ROLES, appointment_id, target, _NOW
                )
                session.commit()
                assert changed.status == target
            else:
                with pytest.raises(InvalidStatusError):
                    change_status(
                        session, clinic_id, actor_id, _ROLES, appointment_id, target, _NOW
                    )
                session.commit()
        with Session(get_engine()) as session:
            row = session.get(Appointment, appointment_id)
            assert row is not None
            if _EXPECTED[(source, target)] == "ok":
                assert row.status == target
                assert _appointment_audits(session) == before + 1
            else:
                assert row.status == source
                assert _appointment_audits(session) == before


def test_a_bad_move_does_not_consult_the_clock(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id)
    earlier = datetime(2026, 10, 14, 8, 0, tzinfo=_ZONE)
    with Session(get_engine()) as session:
        before = _appointment_audits(session)
        with pytest.raises(InvalidStatusError):
            change_status(
                session, clinic_id, actor_id, _ROLES, appointment_id, "completed", earlier
            )
        session.commit()
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.status == "scheduled"
        assert _appointment_audits(session) == before


def test_arrived_is_only_on_the_clinic_day(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id)
    allowed = datetime(2026, 10, 15, 0, 1, tzinfo=_ZONE)
    too_early = datetime(2026, 10, 14, 23, 59, tzinfo=_ZONE)
    too_late = datetime(2026, 10, 16, 0, 1, tzinfo=_ZONE)
    _expect_time_code(clinic_id, actor_id, appointment_id, "arrived", too_early, "not_today")
    _expect_time_code(clinic_id, actor_id, appointment_id, "arrived", too_late, "not_today")
    with Session(get_engine()) as session:
        changed = change_status(
            session, clinic_id, actor_id, _ROLES, appointment_id, "arrived", allowed
        )
        session.commit()
    assert changed.status == "arrived"


def test_no_show_starts_at_the_visit_instant(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id)
    _expect_time_code(
        clinic_id,
        actor_id,
        appointment_id,
        "no_show",
        _START - timedelta(minutes=1),
        "not_started",
    )
    with Session(get_engine()) as session:
        changed = change_status(
            session, clinic_id, actor_id, _ROLES, appointment_id, "no_show", _START
        )
        session.commit()
    assert changed.status == "no_show"


def test_london_clock_change_uses_the_clinic_date(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    _set_timezone(clinic_id, "Europe/London")
    fall_start = datetime(2026, 10, 25, 12, 0, tzinfo=_LONDON)
    fall_id = _insert(clinic_id, patient_id, clinician_id, type_id, fall_start)
    # 00:30 BST is still the previous UTC date. The clinic date is 25 October.
    during_fallback = datetime(2026, 10, 25, 0, 30, tzinfo=_LONDON)
    before_fallback_day = datetime(2026, 10, 24, 23, 59, tzinfo=_LONDON)
    _expect_time_code(clinic_id, actor_id, fall_id, "arrived", before_fallback_day, "not_today")
    with Session(get_engine()) as session:
        changed = change_status(
            session, clinic_id, actor_id, _ROLES, fall_id, "arrived", during_fallback
        )
        session.commit()
    assert changed.status == "arrived"

    spring_start = datetime(2026, 3, 29, 10, 0, tzinfo=_LONDON)
    spring_id = _insert(clinic_id, patient_id, clinician_id, type_id, spring_start)
    before_spring_day = datetime(2026, 3, 28, 23, 59, tzinfo=_LONDON)
    after_spring_midnight = datetime(2026, 3, 29, 0, 1, tzinfo=_LONDON)
    _expect_time_code(clinic_id, actor_id, spring_id, "arrived", before_spring_day, "not_today")
    with Session(get_engine()) as session:
        changed = change_status(
            session, clinic_id, actor_id, _ROLES, spring_id, "arrived", after_spring_midnight
        )
        session.commit()
    assert changed.status == "arrived"


def test_start_and_complete_do_not_use_the_clock(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id)
    _set_status(appointment_id, "arrived")
    later = datetime(2026, 10, 20, 9, 0, tzinfo=_ZONE)
    with Session(get_engine()) as session:
        started = change_status(
            session, clinic_id, actor_id, _ROLES, appointment_id, "in_progress", later
        )
        session.commit()
        finished = change_status(
            session, clinic_id, actor_id, _ROLES, appointment_id, "completed", later
        )
        session.commit()
    assert started.status == "in_progress"
    assert finished.status == "completed"


def test_status_change_writes_one_audit_without_values(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id)
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, appointment_id, "arrived", _NOW)
        session.commit()
    with Session(get_engine()) as session:
        events = AuditRepository(session, clinic_id).list_for_entity("appointment", appointment_id)
        assert [event.action for event in events] == ["create", "status_change"]
        change = events[1]
        assert change.entity_type == "appointment"
        assert change.changed_fields == ["status"]
        assert change.actor_user_id == actor_id
        row = (
            session.execute(text("SELECT * FROM audit_event WHERE action = 'status_change'"))
            .mappings()
            .one()
        )
        stored = " ".join(str(value) for value in row.values())
    assert _NAME not in stored
    assert "scheduled" not in stored
    assert "arrived" not in stored


def test_a_failed_audit_write_does_not_save_the_status(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id)
    with Session(get_engine()) as session:
        with pytest.raises(IntegrityError):
            change_status(session, clinic_id, uuid4(), _ROLES, appointment_id, "arrived", _NOW)
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.status == "scheduled"
        assert _appointment_audits(session) == 1


def test_an_inactive_patient_can_still_change_status(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id)
    with Session(get_engine()) as session:
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        changed = change_status(
            session, clinic_id, actor_id, _ROLES, appointment_id, "arrived", _NOW
        )
        session.commit()
    assert changed.status == "arrived"


def test_no_show_frees_the_slot_and_the_other_statuses_keep_it(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    appointment_id = _book(clinic_id, actor_id, patient_id, clinician_id, type_id)
    with Session(get_engine()) as session:
        second = register_patient(session, clinic_id, actor_id, "Sample Bea", "9000000002", None)
        session.commit()
        second_id = second.id
    for target, source in (
        ("arrived", "scheduled"),
        ("in_progress", "arrived"),
        ("completed", "in_progress"),
    ):
        _set_status(appointment_id, source)
        with Session(get_engine()) as session:
            change_status(session, clinic_id, actor_id, _ROLES, appointment_id, target, _NOW)
            session.commit()
        _assert_slot_blocked(clinic_id, actor_id, clinician_id, second_id, type_id)
    _set_status(appointment_id, "scheduled")
    with Session(get_engine()) as session:
        change_status(session, clinic_id, actor_id, _ROLES, appointment_id, "no_show", _NOW)
        session.commit()
        slots = find_availability(
            session, clinic_id, clinician_id, type_id, _START.date(), _BOOK_NOW
        )
        assert any(slot.starts_at == _START for slot in slots.slots)
        book_appointment(
            session, clinic_id, actor_id, second_id, clinician_id, type_id, _START, _BOOK_NOW
        )
        session.commit()


def _expect_time_code(
    clinic_id: UUID,
    actor_id: UUID,
    appointment_id: UUID,
    target: str,
    now: datetime,
    code: str,
) -> None:
    with Session(get_engine()) as session:
        before = _appointment_audits(session)
        with pytest.raises(AppointmentFieldError) as caught:
            change_status(session, clinic_id, actor_id, _ROLES, appointment_id, target, now)
        session.commit()
    assert caught.value.field == "status"
    assert caught.value.code == code
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        assert row.status == "scheduled"
        assert _appointment_audits(session) == before


def _assert_slot_blocked(
    clinic_id: UUID,
    actor_id: UUID,
    clinician_id: UUID,
    patient_id: UUID,
    type_id: UUID,
) -> None:
    with Session(get_engine()) as session:
        slots = find_availability(
            session, clinic_id, clinician_id, type_id, _START.date(), _BOOK_NOW
        )
        assert not any(slot.starts_at == _START for slot in slots.slots)
        with pytest.raises(SlotTakenError):
            book_appointment(
                session, clinic_id, actor_id, patient_id, clinician_id, type_id, _START, _BOOK_NOW
            )
        session.rollback()


def _world() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "desk@x.test",
            "Sample Desk",
            "synthetic-password-marker",
            ["clinician"],
        )
        clinician = create_user(
            session,
            clinic.id,
            "clinician@x.test",
            "Sample Clinician",
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
        return clinic.id, actor.id, clinician.id, patient.id, consultation.id


def _book(
    clinic_id: UUID,
    actor_id: UUID,
    patient_id: UUID,
    clinician_id: UUID,
    type_id: UUID,
) -> UUID:
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            clinician_id,
            type_id,
            _START,
            _BOOK_NOW,
        )
        session.commit()
        return created.id


def _insert(
    clinic_id: UUID,
    patient_id: UUID,
    clinician_id: UUID,
    type_id: UUID,
    start: datetime,
) -> UUID:
    visit_id = uuid4()
    with Session(get_engine()) as session:
        AppointmentRepository(session, clinic_id).add(
            Appointment(
                id=visit_id,
                patient_id=patient_id,
                clinician_user_id=clinician_id,
                appointment_type_id=type_id,
                starts_at=start,
                ends_at=start + timedelta(minutes=30),
                status="scheduled",
            )
        )
        session.commit()
    return visit_id


def _set_status(appointment_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(Appointment, appointment_id)
        assert row is not None
        row.status = status
        session.commit()


def _set_timezone(clinic_id: UUID, timezone_name: str) -> None:
    with Session(get_engine()) as session:
        clinic = session.get(Clinic, clinic_id)
        assert clinic is not None
        clinic.timezone = timezone_name
        session.commit()


def _appointment_audits(session: Session) -> int:
    count = session.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "appointment")
    )
    return int(count or 0)
