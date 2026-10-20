"""List, create and update appointment types for one clinic."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.domain.clinic_day import ClinicDayValidationError, validate_optional_duration
from dentacircle.domain.recall import recall_months_problem
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.repositories.appointment_type_repository import AppointmentTypeRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.services.clinic_day_service import ClinicNotFoundError

MAX_TYPE_NAME_LENGTH = 200


class ConflictError(Exception):
    """The name is already used in this clinic. The message shown to the client is fixed."""


class InvalidAppointmentTypeError(Exception):
    """A blank name or a duration outside the allowed range."""


class AppointmentTypeNotFoundError(Exception):
    """No type with this id in the caller's clinic."""


@dataclass(frozen=True)
class AppointmentTypeView:
    id: UUID
    name: str
    duration_minutes: int | None
    recall_after_months: int | None
    effective_duration_minutes: int
    is_active: bool


def list_appointment_types(
    session: Session, clinic_id: UUID, include_inactive: bool
) -> list[AppointmentTypeView]:
    default_minutes = _clinic_default(session, clinic_id)
    rows = AppointmentTypeRepository(session, clinic_id).list_types(include_inactive)
    return [_view(row, default_minutes) for row in rows]


def create_appointment_type(
    session: Session,
    clinic_id: UUID,
    name: str,
    duration_minutes: int | None,
    recall_after_months: int | None = None,
) -> AppointmentTypeView:
    cleaned = clean_type_name(name)
    _checked_duration(duration_minutes)
    _checked_recall_months(recall_after_months)
    repository = AppointmentTypeRepository(session, clinic_id)
    if repository.find_by_name(cleaned) is not None:
        raise ConflictError
    repository.add(
        AppointmentType(
            id=uuid4(),
            name=cleaned,
            duration_minutes=duration_minutes,
            recall_after_months=recall_after_months,
            is_active=True,
        )
    )
    _flush_name(session)
    return _require_view(session, clinic_id, repository.find_by_name(cleaned))


def update_appointment_type(
    session: Session,
    clinic_id: UUID,
    type_id: UUID,
    name: str,
    duration_minutes: int | None,
    is_active: bool,
    recall_after_months: int | None = None,
    *,
    set_recall_after_months: bool = False,
) -> AppointmentTypeView:
    cleaned = clean_type_name(name)
    _checked_duration(duration_minutes)
    if set_recall_after_months:
        _checked_recall_months(recall_after_months)
    repository = AppointmentTypeRepository(session, clinic_id)
    row = repository.get(type_id)
    if row is None:
        raise AppointmentTypeNotFoundError
    taken = repository.find_by_name(cleaned)
    if taken is not None and taken.id != row.id:
        raise ConflictError
    row.name = cleaned
    row.duration_minutes = duration_minutes
    row.is_active = is_active
    if set_recall_after_months:
        row.recall_after_months = recall_after_months
    _flush_name(session)
    return _view(row, _clinic_default(session, clinic_id))


def clean_type_name(name: str) -> str:
    trimmed = name.strip()
    if not trimmed or len(trimmed) > MAX_TYPE_NAME_LENGTH:
        raise InvalidAppointmentTypeError
    return trimmed


def effective_duration_minutes(duration_minutes: int | None, clinic_default: int) -> int:
    if duration_minutes is None:
        return clinic_default
    return duration_minutes


def _clinic_default(session: Session, clinic_id: UUID) -> int:
    clinic = ClinicDayRepository(session, clinic_id).get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    return clinic.default_appointment_minutes


def _view(row: AppointmentType, clinic_default: int) -> AppointmentTypeView:
    return AppointmentTypeView(
        id=row.id,
        name=row.name,
        duration_minutes=row.duration_minutes,
        recall_after_months=row.recall_after_months,
        effective_duration_minutes=effective_duration_minutes(row.duration_minutes, clinic_default),
        is_active=row.is_active,
    )


def _require_view(
    session: Session, clinic_id: UUID, row: AppointmentType | None
) -> AppointmentTypeView:
    if row is None:
        raise AppointmentTypeNotFoundError
    return _view(row, _clinic_default(session, clinic_id))


def _flush_name(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        if _is_unique_violation(exc):
            raise ConflictError from None
        raise InvalidAppointmentTypeError from None


def _checked_duration(minutes: int | None) -> None:
    try:
        validate_optional_duration(minutes)
    except ClinicDayValidationError:
        raise InvalidAppointmentTypeError from None


def _checked_recall_months(months: int | None) -> None:
    if recall_months_problem(months) is not None:
        raise InvalidAppointmentTypeError


def _is_unique_violation(exc: IntegrityError) -> bool:
    return isinstance(exc.orig, UniqueViolation)
