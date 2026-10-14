"""Calendar list: clinic-local days, hidden cancellations, and a clinician filter."""

from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.appointment import AppointmentFieldError, calendar_range_problem
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.clinic import Clinic
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.services.appointment_service import list_calendar
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_LONDON = ZoneInfo("Europe/London")
_NOW = datetime(2026, 10, 14, 8, 0, tzinfo=_ZONE)
_TODAY = date(2026, 10, 14)


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_a_week_is_allowed_and_longer_or_backwards_ranges_are_not() -> None:
    assert calendar_range_problem(_TODAY, _TODAY + timedelta(days=6), _ZONE, _NOW) is None
    assert calendar_range_problem(_TODAY, _TODAY, _ZONE, _NOW) is None
    assert calendar_range_problem(_TODAY - timedelta(days=3), _TODAY, _ZONE, _NOW) is None
    assert calendar_range_problem(_TODAY, _TODAY - timedelta(days=1), _ZONE, _NOW) == "before_from"
    assert (
        calendar_range_problem(_TODAY, _TODAY + timedelta(days=7), _ZONE, _NOW) == "span_too_long"
    )
    assert (
        calendar_range_problem(
            _TODAY + timedelta(days=366), _TODAY + timedelta(days=366), _ZONE, _NOW
        )
        == "beyond_horizon"
    )


def test_the_list_includes_both_edges_and_a_visit_that_crosses_midnight(database: str) -> None:
    clinic_id, _actor, clinician_id, patient_id, type_id = _world()
    _set_timezone(clinic_id, "Europe/London")
    now = datetime(2026, 10, 25, 12, 0, tzinfo=_LONDON)
    day = date(2026, 10, 25)
    crossing = _visit(
        clinic_id,
        patient_id,
        clinician_id,
        type_id,
        datetime(2026, 10, 24, 23, 30, tzinfo=_LONDON),
        datetime(2026, 10, 25, 0, 20, tzinfo=_LONDON),
    )
    on_day = _visit(
        clinic_id,
        patient_id,
        clinician_id,
        type_id,
        datetime(2026, 10, 25, 9, 0, tzinfo=_LONDON),
        datetime(2026, 10, 25, 9, 30, tzinfo=_LONDON),
    )
    _visit(
        clinic_id,
        patient_id,
        clinician_id,
        type_id,
        datetime(2026, 10, 24, 9, 0, tzinfo=_LONDON),
        datetime(2026, 10, 24, 9, 30, tzinfo=_LONDON),
    )
    _visit(
        clinic_id,
        patient_id,
        clinician_id,
        type_id,
        datetime(2026, 10, 26, 9, 0, tzinfo=_LONDON),
        datetime(2026, 10, 26, 9, 30, tzinfo=_LONDON),
    )
    with Session(get_engine()) as session:
        rows = list_calendar(session, clinic_id, day, day, None, now)
    assert [row.id for row in rows] == [crossing, on_day]
    # 23:30 the evening before the change is still BST. 09:00 that morning is GMT.
    assert rows[0].starts_at.utcoffset() == timedelta(hours=1)
    assert rows[1].starts_at.utcoffset() == timedelta(0)


def test_same_start_times_sort_by_id_and_cancelled_is_hidden(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    other = _clinician(clinic_id, "two@x.test", "Second Clinician")
    with Session(get_engine()) as session:
        second = register_patient(session, clinic_id, actor_id, "Sample Bea", "9000000002", None)
        session.commit()
        second_id = second.id
    later_id = UUID("00000000-0000-4000-8000-000000000002")
    earlier_id = UUID("00000000-0000-4000-8000-000000000001")
    start = datetime(2026, 10, 14, 10, 0, tzinfo=_ZONE)
    end = start + timedelta(minutes=30)
    _visit(clinic_id, patient_id, clinician_id, type_id, start, end, appointment_id=later_id)
    _visit(clinic_id, second_id, other, type_id, start, end, appointment_id=earlier_id)
    _visit(
        clinic_id,
        patient_id,
        clinician_id,
        type_id,
        start + timedelta(hours=1),
        end + timedelta(hours=1),
        status="cancelled",
    )
    for index, status in enumerate(("arrived", "in_progress", "completed", "no_show"), start=2):
        _visit(
            clinic_id,
            patient_id,
            clinician_id,
            type_id,
            start + timedelta(hours=index),
            end + timedelta(hours=index),
            status=status,
        )
    with Session(get_engine()) as session:
        rows = list_calendar(session, clinic_id, _TODAY, _TODAY, None, _NOW)
    assert rows[0].id == earlier_id
    assert rows[1].id == later_id
    assert "cancelled" not in [row.status for row in rows]
    assert {row.status for row in rows} >= {
        "scheduled",
        "arrived",
        "in_progress",
        "completed",
        "no_show",
    }


def test_a_clinician_filter_and_an_inactive_patient(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    other = _clinician(clinic_id, "two@x.test", "Second Clinician")
    start = datetime(2026, 10, 14, 10, 0, tzinfo=_ZONE)
    end = start + timedelta(minutes=30)
    own = _visit(clinic_id, patient_id, clinician_id, type_id, start, end)
    _visit(
        clinic_id, patient_id, other, type_id, start + timedelta(hours=1), end + timedelta(hours=1)
    )
    with Session(get_engine()) as session:
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
        rows = list_calendar(session, clinic_id, _TODAY, _TODAY, clinician_id, _NOW)
    assert [row.id for row in rows] == [own]
    assert rows[0].patient.full_name == "Sample Ada"
    assert rows[0].patient.display_id == "P-0001"
    assert rows[0].starts_at.isoformat().endswith("+05:30")
    assert rows[0].clinician.full_name == "Sample Clinician"
    assert rows[0].appointment_type.name == "Consultation"


def test_a_bad_range_or_clinician_names_the_field(database: str) -> None:
    clinic_id, _actor, clinician_id, _patient, _type_id = _world()
    other = _other_clinic_clinician()
    idle = _clinician(clinic_id, "idle@x.test", "Ada Idle")
    _deactivate(idle)
    desk = _user(clinic_id, "desk2@x.test", "Ada Desk", ["receptionist"])
    cases: list[tuple[date, date, UUID | None, str, str]] = [
        (_TODAY, _TODAY - timedelta(days=1), None, "to", "before_from"),
        (_TODAY, _TODAY + timedelta(days=7), None, "to", "span_too_long"),
        (
            _TODAY + timedelta(days=366),
            _TODAY + timedelta(days=366),
            None,
            "to",
            "beyond_horizon",
        ),
        (_TODAY, _TODAY, uuid4(), "clinician_id", "unknown"),
        (_TODAY, _TODAY, other, "clinician_id", "unknown"),
        (_TODAY, _TODAY, idle, "clinician_id", "inactive"),
        (_TODAY, _TODAY, desk, "clinician_id", "not_clinician"),
    ]
    for range_from, range_to, clinician_id_case, field, code in cases:
        with Session(get_engine()) as session:
            with pytest.raises(AppointmentFieldError) as caught:
                list_calendar(session, clinic_id, range_from, range_to, clinician_id_case, _NOW)
        assert caught.value.field == field
        assert caught.value.code == code
    with Session(get_engine()) as session:
        listed = list_calendar(session, clinic_id, _TODAY, _TODAY, clinician_id, _NOW)
    assert listed == []


def test_listing_writes_no_audit_event_and_no_row(database: str) -> None:
    clinic_id, _actor, clinician_id, patient_id, type_id = _world()
    _visit(
        clinic_id,
        patient_id,
        clinician_id,
        type_id,
        datetime(2026, 10, 14, 10, 0, tzinfo=_ZONE),
        datetime(2026, 10, 14, 10, 30, tzinfo=_ZONE),
    )
    with Session(get_engine()) as session:
        before_rows = _count(session, Appointment)
        before_audits = _count(session, AuditEvent)
        list_calendar(session, clinic_id, _TODAY, _TODAY, None, _NOW)
        session.commit()
    with Session(get_engine()) as session:
        assert _count(session, Appointment) == before_rows
        assert _count(session, AuditEvent) == before_audits


def test_another_clinic_is_not_listed(database: str) -> None:
    clinic_id, actor_id, clinician_id, patient_id, type_id = _world()
    start = datetime(2026, 10, 14, 10, 0, tzinfo=_ZONE)
    own = _visit(clinic_id, patient_id, clinician_id, type_id, start, start + timedelta(minutes=30))
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        other_actor = create_user(
            session,
            other.id,
            "other@x.test",
            "Other Desk",
            "synthetic-password-marker",
            ["receptionist"],
        )
        other_clinician = create_user(
            session,
            other.id,
            "other-clinician@x.test",
            "Other Clinician",
            "synthetic-password-marker",
            ["clinician"],
        )
        other_patient = register_patient(
            session, other.id, other_actor.id, "Sample Bea", "9000000002", None
        )
        other_type = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == other.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        other_id = other.id
        other_patient_id = other_patient.id
        other_clinician_id = other_clinician.id
        other_type_id = other_type.id
    _visit(
        other_id,
        other_patient_id,
        other_clinician_id,
        other_type_id,
        start,
        start + timedelta(minutes=30),
    )
    with Session(get_engine()) as session:
        rows = list_calendar(session, clinic_id, _TODAY, _TODAY, None, _NOW)
        theirs = list_calendar(session, other_id, _TODAY, _TODAY, None, _NOW)
        with pytest.raises(AppointmentFieldError) as caught:
            list_calendar(session, other_id, _TODAY, _TODAY, clinician_id, _NOW)
    assert [row.id for row in rows] == [own]
    assert own not in [row.id for row in theirs]
    assert caught.value.field == "clinician_id"


def _world() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "desk@x.test",
            "Sample Desk",
            "synthetic-password-marker",
            ["receptionist"],
        )
        clinician = create_user(
            session,
            clinic.id,
            "clinician@x.test",
            "Sample Clinician",
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
        session.commit()
        return clinic.id, actor.id, clinician.id, patient.id, consultation.id


def _visit(
    clinic_id: UUID,
    patient_id: UUID,
    clinician_id: UUID,
    type_id: UUID,
    start: datetime,
    end: datetime,
    *,
    status: str = "scheduled",
    appointment_id: UUID | None = None,
) -> UUID:
    visit_id = uuid4() if appointment_id is None else appointment_id
    with Session(get_engine()) as session:
        AppointmentRepository(session, clinic_id).add(
            Appointment(
                id=visit_id,
                patient_id=patient_id,
                clinician_user_id=clinician_id,
                appointment_type_id=type_id,
                starts_at=start,
                ends_at=end,
                status=status,
            )
        )
        session.commit()
    return visit_id


def _set_timezone(clinic_id: UUID, timezone_name: str) -> None:
    with Session(get_engine()) as session:
        clinic = session.get(Clinic, clinic_id)
        assert clinic is not None
        clinic.timezone = timezone_name
        session.commit()


def _clinician(clinic_id: UUID, email: str, name: str) -> UUID:
    return _user(clinic_id, email, name, ["clinician"])


def _user(clinic_id: UUID, email: str, name: str, roles: list[str]) -> UUID:
    with Session(get_engine()) as session:
        user = create_user(session, clinic_id, email, name, "synthetic-password-marker", roles)
        session.commit()
        return user.id


def _deactivate(user_id: UUID) -> None:
    from dentacircle.models.app_user import AppUser

    with Session(get_engine()) as session:
        user = session.get(AppUser, user_id)
        assert user is not None
        user.is_active = False
        session.commit()


def _other_clinic_clinician() -> UUID:
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Other Synthetic Clinic")
        clinician = create_user(
            session,
            other.id,
            "other-clinician@x.test",
            "Other Clinician",
            "synthetic-password-marker",
            ["clinician"],
        )
        session.commit()
        return clinician.id


def _count(session: Session, model: type[Appointment] | type[AuditEvent]) -> int:
    count = session.scalar(select(func.count()).select_from(model))
    return int(count or 0)
