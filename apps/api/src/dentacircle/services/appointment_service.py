"""List clinicians, find free times, book a visit, change its status, and list what is coming up."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.domain.appointment import (
    MOVABLE_STATUSES,
    SCHEDULED,
    STATUS_TARGET_ROLES,
    STATUS_TRANSITIONS,
    UPCOMING_LIMIT,
    AppointmentFieldError,
    BusySpan,
    OpenInterval,
    arrived_day_problem,
    calendar_range_problem,
    date_problem,
    free_slots,
    may_set_status,
    no_show_time_problem,
    same_instant,
    unavailable_reason,
)
from dentacircle.domain.follow_up import due_on_problem
from dentacircle.domain.patient import display_id
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.patient import Patient
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.repositories.appointment_type_repository import AppointmentTypeRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.repositories.user_repository import UserRepository
from dentacircle.services.audit_service import record
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.follow_up_service import record_incomplete_care
from dentacircle.services.patient_service import PatientNotFoundError

_EXCLUSION_VIOLATION = "23P01"
_CLINICIAN_OVERLAP = "ex_appointment_no_overlap"
_PATIENT_OVERLAP = "ex_appointment_patient_no_overlap"


class AppointmentNotFoundError(Exception):
    """No appointment with this id in the clinic."""


class InvalidStatusError(Exception):
    """The visit cannot take this status, or cannot be cancelled or moved."""


class ForbiddenStatusError(Exception):
    """The caller may not set this status."""


class SlotTakenError(Exception):
    """The clinician's exclusion constraint rejected the row."""


class PatientBusyError(Exception):
    """The patient already has a blocking visit that overlaps this one."""


@dataclass(frozen=True)
class ClinicianView:
    id: UUID
    full_name: str


@dataclass(frozen=True)
class SlotView:
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class AvailabilityView:
    date: date
    timezone: str
    is_open: bool
    duration_minutes: int
    slots: list[SlotView]


@dataclass(frozen=True)
class PartyView:
    id: UUID
    full_name: str


@dataclass(frozen=True)
class TypeNameView:
    id: UUID
    name: str


@dataclass(frozen=True)
class PatientSummaryView:
    id: UUID
    full_name: str
    display_id: str


@dataclass(frozen=True)
class CalendarItemView:
    id: UUID
    starts_at: datetime
    ends_at: datetime
    status: str
    patient: PatientSummaryView
    clinician: PartyView
    appointment_type: TypeNameView


@dataclass(frozen=True)
class AppointmentView:
    id: UUID
    patient_id: UUID
    starts_at: datetime
    ends_at: datetime
    status: str
    clinician: PartyView
    appointment_type: TypeNameView


_RANGE_FIELD = {
    "before_from": "to",
    "span_too_long": "to",
    "beyond_horizon": "to",
}


def list_calendar(
    session: Session,
    clinic_id: UUID,
    range_from: date,
    range_to: date,
    clinician_id: UUID | None,
    now: datetime,
) -> list[CalendarItemView]:
    zone, _timezone_name, _default_minutes = _clinic_clock(session, clinic_id)
    problem = calendar_range_problem(range_from, range_to, zone, now)
    if problem is not None:
        raise AppointmentFieldError(_RANGE_FIELD[problem], problem)
    if clinician_id is not None:
        _require_clinician(session, clinic_id, clinician_id)
    range_start, _from_end = _day_bounds(range_from, zone)
    _to_start, range_end = _day_bounds(range_to, zone)
    rows = AppointmentRepository(session, clinic_id).list_in_range(
        range_start=range_start,
        range_end=range_end,
        clinician_user_id=clinician_id,
    )
    return [
        _calendar_view(appointment, patient, clinician, appointment_type, zone)
        for appointment, patient, clinician, appointment_type in rows
    ]


def get_appointment(
    session: Session,
    clinic_id: UUID,
    appointment_id: UUID,
    now: datetime,
) -> CalendarItemView:
    del now
    zone, _timezone_name, _default_minutes = _clinic_clock(session, clinic_id)
    return _require_detail(session, clinic_id, appointment_id, zone)


def cancel_appointment(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment_id: UUID,
    now: datetime,
) -> CalendarItemView:
    # Cancel does not compare the clock. The argument is here so every appointment
    # write takes the same `now` the route already has.
    del now
    zone, _timezone_name, _default_minutes = _clinic_clock(session, clinic_id)
    repository = AppointmentRepository(session, clinic_id)
    row = repository.get_for_update(appointment_id)
    if row is None:
        raise AppointmentNotFoundError
    if row.status not in MOVABLE_STATUSES:
        raise InvalidStatusError
    row.status = "cancelled"
    record(
        session,
        clinic_id,
        actor_user_id,
        "appointment",
        row.id,
        "status_change",
        changed_fields=["status"],
    )
    session.flush()
    return _require_detail(session, clinic_id, appointment_id, zone)


def change_status(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    actor_roles: Sequence[str],
    appointment_id: UUID,
    target: str,
    now: datetime,
    follow_up_due_on: date | None = None,
) -> CalendarItemView:
    """Lock the visit, apply one allowed status move, and write one audit event.

    Completing the visit may also create or update a follow-up in this same transaction.
    The patient row is locked only after this visit row.
    """
    zone, _timezone_name, _default_minutes = _clinic_clock(session, clinic_id)
    repository = AppointmentRepository(session, clinic_id)
    row = repository.get_for_update(appointment_id)
    if row is None:
        raise AppointmentNotFoundError
    # A target the caller may not set is refused even when the move is also illegal.
    if target in STATUS_TARGET_ROLES and not may_set_status(actor_roles, target):
        raise ForbiddenStatusError
    if follow_up_due_on is not None and target != "completed":
        raise AppointmentFieldError("follow_up_due_on", "only_on_completed")
    # An illegal move is reported before the date window, so a stale Complete
    # stays a status conflict even when the date is also outside the window.
    if target not in STATUS_TRANSITIONS.get(row.status, frozenset()):
        raise InvalidStatusError
    if target == "completed" and follow_up_due_on is not None:
        problem = due_on_problem(follow_up_due_on, zone, now)
        if problem is not None:
            raise AppointmentFieldError("follow_up_due_on", problem)
    problem = _status_time_problem(target, row.starts_at, zone, now)
    if problem is not None:
        raise AppointmentFieldError("status", problem)
    row.status = target
    record(
        session,
        clinic_id,
        actor_user_id,
        "appointment",
        row.id,
        "status_change",
        changed_fields=["status"],
    )
    if target == "completed":
        record_incomplete_care(
            session, clinic_id, actor_user_id, row, zone, now, due_on=follow_up_due_on
        )
    session.flush()
    return _require_detail(session, clinic_id, appointment_id, zone)


def list_clinicians(session: Session, clinic_id: UUID) -> list[ClinicianView]:
    rows = UserRepository(session, clinic_id).list_clinicians()
    return [ClinicianView(id=row.id, full_name=row.full_name) for row in rows]


def find_availability(
    session: Session,
    clinic_id: UUID,
    clinician_id: UUID,
    appointment_type_id: UUID | None,
    day: date,
    now: datetime,
    reschedule_appointment_id: UUID | None = None,
) -> AvailabilityView:
    zone, timezone_name, default_minutes = _clinic_clock(session, clinic_id)
    duration, exclude_id, kept_clinician_id = _availability_duration(
        session, clinic_id, appointment_type_id, reschedule_appointment_id, default_minutes
    )
    if kept_clinician_id is None or clinician_id != kept_clinician_id:
        _require_clinician(session, clinic_id, clinician_id)
    problem = date_problem(day, zone, now)
    if problem is not None:
        raise AppointmentFieldError("date", problem)
    intervals = _intervals(session, clinic_id, day)
    if not intervals:
        return AvailabilityView(
            date=day,
            timezone=timezone_name,
            is_open=False,
            duration_minutes=duration,
            slots=[],
        )
    day_start, day_end = _day_bounds(day, zone)
    busy = [
        BusySpan(start, end)
        for start, end in AppointmentRepository(session, clinic_id).busy_spans(
            span_start=day_start,
            span_end=day_end,
            clinician_user_id=clinician_id,
            exclude_appointment_id=exclude_id,
        )
    ]
    slots = free_slots(intervals, busy, duration, day, zone, now)
    return AvailabilityView(
        date=day,
        timezone=timezone_name,
        is_open=True,
        duration_minutes=duration,
        slots=[SlotView(_in_zone(start, zone), _in_zone(end, zone)) for start, end in slots],
    )


def reschedule_appointment(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment_id: UUID,
    starts_at: datetime,
    clinician_id: UUID | None,
    now: datetime,
) -> CalendarItemView:
    zone, _timezone_name, _default_minutes = _clinic_clock(session, clinic_id)
    repository = AppointmentRepository(session, clinic_id)
    row = repository.get_for_update(appointment_id)
    if row is None:
        raise AppointmentNotFoundError
    if row.status not in MOVABLE_STATUSES:
        raise InvalidStatusError
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise AppointmentFieldError("starts_at", "timezone_naive")
    clinician = (
        _require_clinician(session, clinic_id, clinician_id)
        if clinician_id is not None
        else _kept_clinician(session, clinic_id, row.clinician_user_id)
    )
    if same_instant(starts_at, row.starts_at) and clinician.id == row.clinician_user_id:
        raise AppointmentFieldError("starts_at", "unchanged")
    duration = _length_minutes(row)
    local_day = starts_at.astimezone(zone).date()
    intervals = _intervals(session, clinic_id, local_day)
    reason = unavailable_reason(intervals, duration, local_day, zone, now, starts_at)
    if reason is not None:
        raise AppointmentFieldError("starts_at", reason)
    offered = free_slots(intervals, [], duration, local_day, zone, now)
    start, end = next(slot for slot in offered if same_instant(slot[0], starts_at))
    patient_busy = repository.busy_spans(
        span_start=start,
        span_end=end,
        patient_id=row.patient_id,
        exclude_appointment_id=row.id,
    )
    if patient_busy:
        raise PatientBusyError
    changed = ["starts_at", "ends_at"]
    if clinician.id != row.clinician_user_id:
        changed.append("clinician_user_id")
    row.starts_at = start
    row.ends_at = end
    row.clinician_user_id = clinician.id
    record(
        session,
        clinic_id,
        actor_user_id,
        "appointment",
        row.id,
        "update",
        changed_fields=changed,
    )
    try:
        session.flush()
    except IntegrityError as exc:
        _raise_overlap(exc)
    return _require_detail(session, clinic_id, appointment_id, zone)


def book_appointment(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient_id: UUID,
    clinician_id: UUID,
    appointment_type_id: UUID,
    starts_at: datetime,
    now: datetime,
) -> AppointmentView:
    zone, _timezone_name, default_minutes = _clinic_clock(session, clinic_id)
    _require_patient(session, clinic_id, patient_id)
    clinician = _require_clinician(session, clinic_id, clinician_id)
    appointment_type = _require_type(session, clinic_id, appointment_type_id)
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise AppointmentFieldError("starts_at", "timezone_naive")
    local_day = starts_at.astimezone(zone).date()
    duration = _duration(appointment_type, default_minutes)
    intervals = _intervals(session, clinic_id, local_day)
    reason = unavailable_reason(intervals, duration, local_day, zone, now, starts_at)
    if reason is not None:
        raise AppointmentFieldError("starts_at", reason)
    offered = free_slots(intervals, [], duration, local_day, zone, now)
    match = next(slot for slot in offered if same_instant(slot[0], starts_at))
    start, end = match
    patient_busy = AppointmentRepository(session, clinic_id).busy_spans(
        span_start=start,
        span_end=end,
        patient_id=patient_id,
    )
    if patient_busy:
        raise PatientBusyError
    appointment = Appointment(
        id=uuid4(),
        patient_id=patient_id,
        clinician_user_id=clinician.id,
        appointment_type_id=appointment_type.id,
        starts_at=start,
        ends_at=end,
        status=SCHEDULED,
    )
    AppointmentRepository(session, clinic_id).add(appointment)
    record(
        session,
        clinic_id,
        actor_user_id,
        "appointment",
        appointment.id,
        "create",
        changed_fields=[],
    )
    try:
        session.flush()
    except IntegrityError as exc:
        _raise_overlap(exc)
    session.refresh(appointment)
    return _view(appointment, zone, clinician, appointment_type)


def list_upcoming(
    session: Session,
    clinic_id: UUID,
    patient_id: UUID,
    now: datetime,
) -> list[AppointmentView]:
    zone, _timezone_name, _default_minutes = _clinic_clock(session, clinic_id)
    if PatientRepository(session, clinic_id).get(patient_id) is None:
        raise PatientNotFoundError
    rows = AppointmentRepository(session, clinic_id).upcoming_for_patient(
        patient_id, now, UPCOMING_LIMIT
    )
    users = UserRepository(session, clinic_id)
    types = AppointmentTypeRepository(session, clinic_id)
    views: list[AppointmentView] = []
    for row in rows:
        clinician = users.get(row.clinician_user_id)
        appointment_type = types.get(row.appointment_type_id)
        if clinician is None or appointment_type is None:
            raise RuntimeError("appointment points at a missing clinician or type")
        views.append(_view(row, zone, clinician, appointment_type))
    return views


def _require_patient(session: Session, clinic_id: UUID, patient_id: UUID) -> None:
    patient = PatientRepository(session, clinic_id).get(patient_id)
    if patient is None:
        raise AppointmentFieldError("patient_id", "unknown")
    if patient.status != "active":
        raise AppointmentFieldError("patient_id", "inactive")


def _require_clinician(session: Session, clinic_id: UUID, clinician_id: UUID) -> AppUser:
    users = UserRepository(session, clinic_id)
    user = users.get(clinician_id)
    if user is None:
        raise AppointmentFieldError("clinician_id", "unknown")
    if not user.is_active:
        raise AppointmentFieldError("clinician_id", "inactive")
    clinician = users.get_clinician(clinician_id)
    if clinician is None:
        raise AppointmentFieldError("clinician_id", "not_clinician")
    return clinician


def _require_type(session: Session, clinic_id: UUID, type_id: UUID) -> AppointmentType:
    row = AppointmentTypeRepository(session, clinic_id).get(type_id)
    if row is None:
        raise AppointmentFieldError("appointment_type_id", "unknown")
    if not row.is_active:
        raise AppointmentFieldError("appointment_type_id", "inactive")
    return row


def _availability_duration(
    session: Session,
    clinic_id: UUID,
    appointment_type_id: UUID | None,
    reschedule_appointment_id: UUID | None,
    default_minutes: int,
) -> tuple[int, UUID | None, UUID | None]:
    if (appointment_type_id is None) == (reschedule_appointment_id is None):
        if appointment_type_id is None:
            raise AppointmentFieldError("appointment_type_id", "required")
        raise AppointmentFieldError("reschedule_appointment_id", "exclusive")
    if reschedule_appointment_id is not None:
        found = AppointmentRepository(session, clinic_id).get_detail(reschedule_appointment_id)
        if found is None:
            raise AppointmentFieldError("reschedule_appointment_id", "unknown")
        appointment = found[0]
        if appointment.status not in MOVABLE_STATUSES:
            raise AppointmentFieldError("reschedule_appointment_id", "invalid_status")
        return _length_minutes(appointment), appointment.id, appointment.clinician_user_id
    if appointment_type_id is None:
        raise AppointmentFieldError("appointment_type_id", "required")
    duration = _duration(_require_type(session, clinic_id, appointment_type_id), default_minutes)
    return duration, None, None


def _status_time_problem(
    target: str, starts_at: datetime, zone: ZoneInfo, now: datetime
) -> str | None:
    if target == "arrived":
        return arrived_day_problem(starts_at, zone, now)
    if target == "no_show":
        return no_show_time_problem(starts_at, now)
    return None


def _length_minutes(row: Appointment) -> int:
    elapsed = row.ends_at.astimezone(UTC) - row.starts_at.astimezone(UTC)
    return int(elapsed.total_seconds() // 60)


def _kept_clinician(session: Session, clinic_id: UUID, user_id: UUID) -> AppUser:
    user = UserRepository(session, clinic_id).get(user_id)
    if user is None:
        raise RuntimeError("appointment points at a missing clinician")
    return user


def _duration(appointment_type: AppointmentType, default_minutes: int) -> int:
    if appointment_type.duration_minutes is None:
        return default_minutes
    return appointment_type.duration_minutes


def _intervals(session: Session, clinic_id: UUID, day: date) -> list[OpenInterval]:
    hours = ClinicDayRepository(session, clinic_id).list_hours()
    return [
        OpenInterval(row.opens_at, row.closes_at) for row in hours if row.weekday == day.weekday()
    ]


def _clinic_clock(session: Session, clinic_id: UUID) -> tuple[ZoneInfo, str, int]:
    clinic = ClinicDayRepository(session, clinic_id).get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    try:
        zone = ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        raise ClinicNotFoundError from None
    return zone, clinic.timezone, clinic.default_appointment_minutes


def _day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=zone)
    return start, end


def _in_zone(moment: datetime, zone: ZoneInfo) -> datetime:
    return moment.astimezone(zone)


def _require_detail(
    session: Session,
    clinic_id: UUID,
    appointment_id: UUID,
    zone: ZoneInfo,
) -> CalendarItemView:
    found = AppointmentRepository(session, clinic_id).get_detail(appointment_id)
    if found is None:
        raise AppointmentNotFoundError
    appointment, patient, clinician, appointment_type = found
    return _calendar_view(appointment, patient, clinician, appointment_type, zone)


def _calendar_view(
    row: Appointment,
    patient: Patient,
    clinician: AppUser,
    appointment_type: AppointmentType,
    zone: ZoneInfo,
) -> CalendarItemView:
    return CalendarItemView(
        id=row.id,
        starts_at=_in_zone(row.starts_at, zone),
        ends_at=_in_zone(row.ends_at, zone),
        status=row.status,
        patient=PatientSummaryView(
            id=patient.id,
            full_name=patient.full_name,
            display_id=display_id(patient.patient_number),
        ),
        clinician=PartyView(id=clinician.id, full_name=clinician.full_name),
        appointment_type=TypeNameView(id=appointment_type.id, name=appointment_type.name),
    )


def _view(
    row: Appointment,
    zone: ZoneInfo,
    clinician: AppUser,
    appointment_type: AppointmentType,
) -> AppointmentView:
    return AppointmentView(
        id=row.id,
        patient_id=row.patient_id,
        starts_at=_in_zone(row.starts_at, zone),
        ends_at=_in_zone(row.ends_at, zone),
        status=row.status,
        clinician=PartyView(id=clinician.id, full_name=clinician.full_name),
        appointment_type=TypeNameView(id=appointment_type.id, name=appointment_type.name),
    )


def _raise_overlap(exc: IntegrityError) -> None:
    if getattr(exc.orig, "sqlstate", None) != _EXCLUSION_VIOLATION:
        raise exc
    name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if name == _PATIENT_OVERLAP:
        raise PatientBusyError from None
    if name == _CLINICIAN_OVERLAP:
        raise SlotTakenError from None
    raise exc
