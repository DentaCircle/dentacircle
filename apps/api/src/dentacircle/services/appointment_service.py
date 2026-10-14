"""List clinicians, find free times, book a visit, and list what is coming up."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.domain.appointment import (
    SCHEDULED,
    UPCOMING_LIMIT,
    AppointmentFieldError,
    BusySpan,
    OpenInterval,
    date_problem,
    free_slots,
    same_instant,
    unavailable_reason,
)
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.repositories.appointment_type_repository import AppointmentTypeRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.repositories.user_repository import UserRepository
from dentacircle.services.audit_service import record
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.patient_service import PatientNotFoundError

_EXCLUSION_VIOLATION = "23P01"


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
class AppointmentView:
    id: UUID
    patient_id: UUID
    starts_at: datetime
    ends_at: datetime
    status: str
    clinician: PartyView
    appointment_type: TypeNameView


def list_clinicians(session: Session, clinic_id: UUID) -> list[ClinicianView]:
    rows = UserRepository(session, clinic_id).list_clinicians()
    return [ClinicianView(id=row.id, full_name=row.full_name) for row in rows]


def find_availability(
    session: Session,
    clinic_id: UUID,
    clinician_id: UUID,
    appointment_type_id: UUID,
    day: date,
    now: datetime,
) -> AvailabilityView:
    zone, timezone_name, default_minutes = _clinic_clock(session, clinic_id)
    _require_clinician(session, clinic_id, clinician_id)
    appointment_type = _require_type(session, clinic_id, appointment_type_id)
    problem = date_problem(day, zone, now)
    if problem is not None:
        raise AppointmentFieldError("date", problem)
    duration = _duration(appointment_type, default_minutes)
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
        if _is_exclusion(exc):
            raise SlotTakenError from None
        raise
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


def _is_exclusion(exc: IntegrityError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == _EXCLUSION_VIOLATION
