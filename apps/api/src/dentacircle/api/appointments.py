"""Free times, booking, and a patient's upcoming visits."""

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_core import PydanticCustomError

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.appointment import (
    APPOINTMENT_ROLES,
    APPOINTMENT_STATUSES,
    AppointmentFieldError,
)
from dentacircle.services.appointment_service import (
    AppointmentView,
    AvailabilityView,
    CalendarItemView,
    PatientBusyError,
    SlotTakenError,
    book_appointment,
    find_availability,
    list_calendar,
    list_upcoming,
)
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.patient_service import PatientNotFoundError

router = APIRouter()

can_book = require_roles(*APPOINTMENT_ROLES)

AppointmentStatus = Literal[
    "scheduled", "arrived", "in_progress", "completed", "cancelled", "no_show"
]


class AppointmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID
    clinician_id: UUID
    appointment_type_id: UUID
    starts_at: datetime

    @field_validator("starts_at")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise PydanticCustomError("timezone_naive", "invalid")
        return value


class PartyResponse(BaseModel):
    id: UUID
    full_name: str


class TypeNameResponse(BaseModel):
    id: UUID
    name: str


class PatientSummaryResponse(BaseModel):
    id: UUID
    full_name: str
    display_id: str


class CalendarItemResponse(BaseModel):
    id: UUID
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    patient: PatientSummaryResponse
    clinician: PartyResponse
    appointment_type: TypeNameResponse


class AppointmentResponse(BaseModel):
    id: UUID
    patient_id: UUID
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    clinician: PartyResponse
    appointment_type: TypeNameResponse


class SlotResponse(BaseModel):
    starts_at: datetime
    ends_at: datetime


class AvailabilityResponse(BaseModel):
    date: date
    timezone: str
    is_open: bool
    duration_minutes: int
    slots: list[SlotResponse]


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


_BOOK_ERRORS: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "slot_taken or patient_busy"},
}
_UPCOMING_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
}


def _field_error(exc: AppointmentFieldError, where: str) -> RequestValidationError:
    return RequestValidationError(
        [{"type": exc.code, "loc": (where, exc.field), "msg": exc.code, "input": None}]
    )


def _calendar_item(item: CalendarItemView) -> CalendarItemResponse:
    return CalendarItemResponse(
        id=item.id,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        status=_status(item.status),
        patient=PatientSummaryResponse(
            id=item.patient.id,
            full_name=item.patient.full_name,
            display_id=item.patient.display_id,
        ),
        clinician=PartyResponse(id=item.clinician.id, full_name=item.clinician.full_name),
        appointment_type=TypeNameResponse(
            id=item.appointment_type.id, name=item.appointment_type.name
        ),
    )


def _response(item: AppointmentView) -> AppointmentResponse:
    return AppointmentResponse(
        id=item.id,
        patient_id=item.patient_id,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        status=_status(item.status),
        clinician=PartyResponse(id=item.clinician.id, full_name=item.clinician.full_name),
        appointment_type=TypeNameResponse(
            id=item.appointment_type.id, name=item.appointment_type.name
        ),
    )


def _status(value: str) -> AppointmentStatus:
    if value not in APPOINTMENT_STATUSES:
        raise RuntimeError("appointment status is not one of the known statuses")
    return value  # type: ignore[return-value]


def _availability(found: AvailabilityView) -> AvailabilityResponse:
    return AvailabilityResponse(
        date=found.date,
        timezone=found.timezone,
        is_open=found.is_open,
        duration_minutes=found.duration_minutes,
        slots=[
            SlotResponse(starts_at=slot.starts_at, ends_at=slot.ends_at) for slot in found.slots
        ],
    )


@router.get("/appointments")
def get_appointments(
    user: Annotated[CurrentUser, Depends(can_book)],
    session: SessionDep,
    range_from: Annotated[date, Query(alias="from")],
    range_to: Annotated[date, Query(alias="to")],
    clinician_id: Annotated[UUID | None, Query()] = None,
) -> list[CalendarItemResponse]:
    try:
        rows = list_calendar(
            session,
            user.clinic.id,
            range_from,
            range_to,
            clinician_id,
            datetime.now(UTC),
        )
    except AppointmentFieldError as exc:
        raise _field_error(exc, "query") from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    return [_calendar_item(row) for row in rows]


@router.get("/appointments/availability")
def get_availability(
    user: Annotated[CurrentUser, Depends(can_book)],
    session: SessionDep,
    day: Annotated[date, Query(alias="date")],
    clinician_id: UUID,
    appointment_type_id: UUID,
) -> AvailabilityResponse:
    try:
        found = find_availability(
            session,
            user.clinic.id,
            clinician_id,
            appointment_type_id,
            day,
            datetime.now(UTC),
        )
    except AppointmentFieldError as exc:
        raise _field_error(exc, "query") from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    return _availability(found)


@router.post("/appointments", status_code=201, responses=_BOOK_ERRORS)
def post_appointment(
    body: AppointmentCreate,
    user: Annotated[CurrentUser, Depends(can_book)],
    session: SessionDep,
) -> AppointmentResponse:
    try:
        created = book_appointment(
            session,
            user.clinic.id,
            user.id,
            body.patient_id,
            body.clinician_id,
            body.appointment_type_id,
            body.starts_at,
            datetime.now(UTC),
        )
    except AppointmentFieldError as exc:
        raise _field_error(exc, "body") from None
    except SlotTakenError:
        raise CodedHttpError(409, "slot_taken", "That time was just taken.") from None
    except PatientBusyError:
        raise CodedHttpError(
            409, "patient_busy", "That patient already has an appointment then."
        ) from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    session.commit()
    return _response(created)


@router.get("/patients/{patient_id}/appointments", responses=_UPCOMING_ERRORS)
def get_patient_appointments(
    patient_id: UUID,
    user: Annotated[CurrentUser, Depends(can_book)],
    session: SessionDep,
) -> list[AppointmentResponse]:
    try:
        rows = list_upcoming(session, user.clinic.id, patient_id, datetime.now(UTC))
    except PatientNotFoundError:
        raise HTTPException(status_code=404) from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    return [_response(row) for row in rows]
