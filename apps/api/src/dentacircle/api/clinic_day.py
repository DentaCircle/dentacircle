"""Read and replace the clinic's timezone, default duration and open intervals."""

from datetime import time
from typing import Annotated, Self

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.domain.clinic_day import (
    MAX_DURATION_MINUTES,
    MIN_DURATION_MINUTES,
    ClinicDayValidationError,
    validate_timezone,
    validate_working_hours,
)
from dentacircle.domain.roles import ROLES
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import (
    ClinicDay,
    ClinicNotFoundError,
    read_clinic_day,
    replace_clinic_day,
)

router = APIRouter()

any_signed_in_user = require_roles(*ROLES)
clinic_admin_only = require_roles("clinic_admin")


class WorkingHoursInterval(BaseModel):
    weekday: int = Field(ge=0, le=6)
    opens_at: time
    closes_at: time

    @model_validator(mode="after")
    def opens_before_close(self) -> Self:
        if self.opens_at >= self.closes_at:
            raise ValueError("opens_before_closes")
        return self


class ClinicDayBody(BaseModel):
    timezone: str
    default_appointment_minutes: int = Field(ge=MIN_DURATION_MINUTES, le=MAX_DURATION_MINUTES)
    working_hours: list[WorkingHoursInterval]

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            validate_timezone(value)
        except ClinicDayValidationError:
            raise ValueError("unknown_timezone") from None
        return value

    @model_validator(mode="after")
    def hours_fit(self) -> Self:
        try:
            validate_working_hours(
                [(item.weekday, item.opens_at, item.closes_at) for item in self.working_hours]
            )
        except ClinicDayValidationError as exc:
            raise ValueError(exc.code) from None
        return self


class WorkingHoursResponse(BaseModel):
    weekday: int
    opens_at: time
    closes_at: time


class ClinicDayResponse(BaseModel):
    timezone: str
    default_appointment_minutes: int
    working_hours: list[WorkingHoursResponse]


def _response(day: ClinicDay) -> ClinicDayResponse:
    return ClinicDayResponse(
        timezone=day.timezone,
        default_appointment_minutes=day.default_appointment_minutes,
        working_hours=[
            WorkingHoursResponse(
                weekday=item.weekday, opens_at=item.opens_at, closes_at=item.closes_at
            )
            for item in day.working_hours
        ],
    )


@router.get("/clinic/day")
def get_clinic_day(
    user: Annotated[CurrentUser, Depends(any_signed_in_user)],
    session: SessionDep,
) -> ClinicDayResponse:
    try:
        day = read_clinic_day(session, user.clinic.id)
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    return _response(day)


@router.put("/clinic/day")
def put_clinic_day(
    body: ClinicDayBody,
    user: Annotated[CurrentUser, Depends(clinic_admin_only)],
    session: SessionDep,
) -> ClinicDayResponse:
    try:
        day = replace_clinic_day(
            session,
            user.clinic.id,
            body.timezone,
            body.default_appointment_minutes,
            [(item.weekday, item.opens_at, item.closes_at) for item in body.working_hours],
        )
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    except ClinicDayValidationError:
        raise HTTPException(status_code=422) from None
    session.commit()
    return _response(day)
