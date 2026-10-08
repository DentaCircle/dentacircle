"""Register and list patients. Detail and edit are a later slice."""

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.domain.patient import (
    MAX_NAME_LENGTH,
    MAX_PHONE_LENGTH,
    PATIENT_ROLES,
    PatientFieldError,
    clean_phone,
)
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.patient_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PatientView,
    list_patients,
    register_patient,
)

router = APIRouter()

can_use_patients = require_roles(*PATIENT_ROLES)


def _trimmed(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class PatientCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    phone: str = Field(min_length=1, max_length=MAX_PHONE_LENGTH)
    date_of_birth: date | None = None

    @field_validator("full_name", "phone", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return _trimmed(value)

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        try:
            clean_phone(value)
        except PatientFieldError as exc:
            raise PydanticCustomError(exc.code, "invalid") from None
        return value


class PatientResponse(BaseModel):
    id: UUID
    patient_number: int
    display_id: str
    full_name: str
    phone: str
    date_of_birth: date | None
    created_at: datetime


class PatientListResponse(BaseModel):
    items: list[PatientResponse]
    total: int
    page: int
    page_size: int


def _response(item: PatientView) -> PatientResponse:
    return PatientResponse(
        id=item.id,
        patient_number=item.patient_number,
        display_id=item.display_id,
        full_name=item.full_name,
        phone=item.phone,
        date_of_birth=item.date_of_birth,
        created_at=item.created_at,
    )


def _field_error(exc: PatientFieldError) -> RequestValidationError:
    return RequestValidationError(
        [{"type": exc.code, "loc": ("body", exc.field), "msg": exc.code, "input": None}]
    )


@router.post("/patients", status_code=201)
def post_patient(
    body: PatientCreate,
    user: Annotated[CurrentUser, Depends(can_use_patients)],
    session: SessionDep,
) -> PatientResponse:
    try:
        created = register_patient(
            session,
            user.clinic.id,
            user.id,
            body.full_name,
            body.phone,
            body.date_of_birth,
        )
    except PatientFieldError as exc:
        raise _field_error(exc) from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    session.commit()
    return _response(created)


@router.get("/patients")
def get_patients(
    user: Annotated[CurrentUser, Depends(can_use_patients)],
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    q: str | None = None,
) -> PatientListResponse:
    found = list_patients(session, user.clinic.id, q, page, page_size)
    return PatientListResponse(
        items=[_response(item) for item in found.items],
        total=found.total,
        page=found.page,
        page_size=found.page_size,
    )
