"""Read or create the one open follow-up for a patient."""

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.follow_up import FOLLOW_UP_CREATE_ROLES, FOLLOW_UP_READ_ROLES
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.follow_up_service import (
    FollowUpFieldError,
    FollowUpOpenError,
    FollowUpView,
    PatientInactiveError,
    create_manual_follow_up,
    get_open_follow_up,
)
from dentacircle.services.patient_service import PatientNotFoundError, get_patient

router = APIRouter()

can_read = require_roles(*FOLLOW_UP_READ_ROLES)
can_create = require_roles(*FOLLOW_UP_CREATE_ROLES)

FollowUpStatus = Literal["scheduled", "contacted", "booked"]


class FollowUpBody(BaseModel):
    id: UUID
    patient_id: UUID
    appointment_id: UUID | None
    status: FollowUpStatus
    due_on: date
    created_at: datetime


class CreateFollowUpBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    due_on: date


class FollowUpResponse(BaseModel):
    follow_up: FollowUpBody | None


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
}
_CREATE_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
    409: {"model": ErrorResponse, "description": "follow_up_open or patient_inactive"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}


@router.get("/patients/{patient_id}/follow-up", responses=_READ_ERRORS)
def get_follow_up(
    patient_id: UUID,
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
) -> FollowUpResponse:
    try:
        found = get_open_follow_up(session, user.clinic.id, patient_id)
    except PatientNotFoundError:
        raise HTTPException(status_code=404) from None
    return FollowUpResponse(follow_up=None if found is None else _body(found))


def _patient_for_create(
    patient_id: UUID,
    user: Annotated[CurrentUser, Depends(can_create)],
    session: SessionDep,
) -> UUID:
    """404 before the body is read, so a missing patient is not a validation error."""
    try:
        get_patient(session, user.clinic.id, patient_id)
    except PatientNotFoundError:
        raise HTTPException(status_code=404) from None
    return patient_id


@router.post(
    "/patients/{patient_id}/follow-up",
    status_code=201,
    responses=_CREATE_ERRORS,
)
def post_follow_up(
    patient_id: Annotated[UUID, Depends(_patient_for_create)],
    body: CreateFollowUpBody,
    user: Annotated[CurrentUser, Depends(can_create)],
    session: SessionDep,
) -> FollowUpResponse:
    try:
        created = create_manual_follow_up(
            session,
            user.clinic.id,
            user.id,
            patient_id,
            body.due_on,
            datetime.now(UTC),
        )
    except FollowUpFieldError as exc:
        raise _field_error(exc) from None
    except PatientNotFoundError:
        raise HTTPException(status_code=404) from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    except PatientInactiveError:
        raise CodedHttpError(409, "patient_inactive", "This patient is inactive.") from None
    except FollowUpOpenError:
        raise CodedHttpError(409, "follow_up_open", "Already has an open follow-up.") from None
    session.commit()
    return FollowUpResponse(follow_up=_body(created))


def _field_error(exc: FollowUpFieldError) -> RequestValidationError:
    return RequestValidationError(
        [{"type": exc.code, "loc": ("body", exc.field), "msg": exc.code, "input": None}]
    )


def _body(row: FollowUpView) -> FollowUpBody:
    return FollowUpBody(
        id=row.id,
        patient_id=row.patient_id,
        appointment_id=row.appointment_id,
        status=_status(row.status),
        due_on=row.due_on,
        created_at=row.created_at,
    )


def _status(value: str) -> FollowUpStatus:
    if value not in ("scheduled", "contacted", "booked"):
        raise RuntimeError("follow-up status is not one of the open statuses")
    return value  # type: ignore[return-value]
