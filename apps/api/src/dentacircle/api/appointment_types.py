"""List, create and update appointment types. There is no delete."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.domain.clinic_day import MAX_DURATION_MINUTES, MIN_DURATION_MINUTES
from dentacircle.domain.roles import ROLES
from dentacircle.services.appointment_type_service import (
    MAX_TYPE_NAME_LENGTH,
    AppointmentTypeNotFoundError,
    AppointmentTypeView,
    ConflictError,
    InvalidAppointmentTypeError,
    create_appointment_type,
    list_appointment_types,
    update_appointment_type,
)
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError

router = APIRouter()

any_signed_in_user = require_roles(*ROLES)
clinic_admin_only = require_roles("clinic_admin")


def _trimmed(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class AppointmentTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_TYPE_NAME_LENGTH)
    duration_minutes: int | None = Field(
        default=None, ge=MIN_DURATION_MINUTES, le=MAX_DURATION_MINUTES
    )

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return _trimmed(value)


class AppointmentTypeUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_TYPE_NAME_LENGTH)
    duration_minutes: int | None = Field(ge=MIN_DURATION_MINUTES, le=MAX_DURATION_MINUTES)
    is_active: bool

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return _trimmed(value)


class AppointmentTypeResponse(BaseModel):
    id: UUID
    name: str
    duration_minutes: int | None
    effective_duration_minutes: int
    is_active: bool


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


_APPOINTMENT_TYPE_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
    409: {"model": ErrorResponse, "description": "Conflict"},
}


def _response(item: AppointmentTypeView) -> AppointmentTypeResponse:
    return AppointmentTypeResponse(
        id=item.id,
        name=item.name,
        duration_minutes=item.duration_minutes,
        effective_duration_minutes=item.effective_duration_minutes,
        is_active=item.is_active,
    )


@router.get("/appointment-types")
def get_appointment_types(
    user: Annotated[CurrentUser, Depends(any_signed_in_user)],
    session: SessionDep,
    include_inactive: bool = False,
) -> list[AppointmentTypeResponse]:
    try:
        rows = list_appointment_types(session, user.clinic.id, include_inactive)
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    return [_response(row) for row in rows]


@router.post("/appointment-types", status_code=201, responses=_APPOINTMENT_TYPE_ERRORS)
def post_appointment_type(
    body: AppointmentTypeCreate,
    user: Annotated[CurrentUser, Depends(clinic_admin_only)],
    session: SessionDep,
) -> AppointmentTypeResponse:
    try:
        created = create_appointment_type(session, user.clinic.id, body.name, body.duration_minutes)
    except ConflictError:
        raise HTTPException(status_code=409) from None
    except InvalidAppointmentTypeError:
        raise HTTPException(status_code=422) from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    session.commit()
    return _response(created)


@router.put("/appointment-types/{type_id}", responses=_APPOINTMENT_TYPE_ERRORS)
def put_appointment_type(
    type_id: UUID,
    body: AppointmentTypeUpdate,
    user: Annotated[CurrentUser, Depends(clinic_admin_only)],
    session: SessionDep,
) -> AppointmentTypeResponse:
    try:
        updated = update_appointment_type(
            session,
            user.clinic.id,
            type_id,
            body.name,
            body.duration_minutes,
            body.is_active,
        )
    except AppointmentTypeNotFoundError:
        raise HTTPException(status_code=404) from None
    except ConflictError:
        raise HTTPException(status_code=409) from None
    except InvalidAppointmentTypeError:
        raise HTTPException(status_code=422) from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    session.commit()
    return _response(updated)
