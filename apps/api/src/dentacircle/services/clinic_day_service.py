"""Read and replace one clinic's timezone, default duration and open intervals."""

from dataclasses import dataclass
from datetime import time
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.domain.clinic_day import (
    DEFAULT_APPOINTMENT_MINUTES,
    DEFAULT_APPOINTMENT_TYPES,
    DEFAULT_TIMEZONE,
    DEFAULT_WORKING_HOURS,
    ClinicDayValidationError,
    validate_duration,
    validate_timezone,
    validate_working_hours,
)
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.repositories.appointment_type_repository import AppointmentTypeRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository


@dataclass(frozen=True)
class WorkingHoursView:
    weekday: int
    opens_at: time
    closes_at: time


@dataclass(frozen=True)
class ClinicDay:
    timezone: str
    default_appointment_minutes: int
    working_hours: list[WorkingHoursView]


class ClinicNotFoundError(Exception):
    """The session clinic has no row. Callers turn this into 404."""


def read_clinic_day(session: Session, clinic_id: UUID) -> ClinicDay:
    repository = ClinicDayRepository(session, clinic_id)
    clinic = repository.get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    return ClinicDay(
        timezone=clinic.timezone,
        default_appointment_minutes=clinic.default_appointment_minutes,
        working_hours=[
            WorkingHoursView(row.weekday, row.opens_at, row.closes_at)
            for row in repository.list_hours()
        ],
    )


def replace_clinic_day(
    session: Session,
    clinic_id: UUID,
    timezone: str,
    default_appointment_minutes: int,
    working_hours: list[tuple[int, time, time]],
) -> ClinicDay:
    validate_timezone(timezone)
    validate_duration(default_appointment_minutes)
    validate_working_hours(working_hours)
    repository = ClinicDayRepository(session, clinic_id)
    clinic = repository.get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    clinic.timezone = timezone
    clinic.default_appointment_minutes = default_appointment_minutes
    repository.replace_hours(working_hours)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ClinicDayValidationError("interval_overlap") from None
    return read_clinic_day(session, clinic_id)


def seed_clinic_day(session: Session, clinic_id: UUID) -> None:
    """Starting hours and types for a clinic that was just created. Not run again."""
    repository = ClinicDayRepository(session, clinic_id)
    clinic = repository.get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    clinic.timezone = DEFAULT_TIMEZONE
    clinic.default_appointment_minutes = DEFAULT_APPOINTMENT_MINUTES
    repository.replace_hours(
        [(item.weekday, item.opens_at, item.closes_at) for item in DEFAULT_WORKING_HOURS]
    )
    types = AppointmentTypeRepository(session, clinic_id)
    for item in DEFAULT_APPOINTMENT_TYPES:
        types.add(
            AppointmentType(
                id=uuid4(),
                name=item.name,
                duration_minutes=item.duration_minutes,
                is_active=True,
            )
        )
    session.flush()
