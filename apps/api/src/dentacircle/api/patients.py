"""Register, list, read and edit patients."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator
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
    PatientChanges,
    PatientNotFoundError,
    PatientView,
    edit_patient,
    get_patient,
    list_patients,
    register_patient,
    set_patient_status,
)

router = APIRouter()

can_use_patients = require_roles(*PATIENT_ROLES)

# OFFSET is a PostgreSQL bigint. Cap page so (page - 1) * page_size stays in range
# even when page_size is the maximum.
MAX_PAGE = (2**63 - 1) // MAX_PAGE_SIZE + 1


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


class PatientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    phone: str | None = Field(default=None, min_length=1, max_length=MAX_PHONE_LENGTH)
    date_of_birth: date | None = None

    @field_validator("full_name", "phone", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return _trimmed(value)

    @field_validator("full_name", "phone")
    @classmethod
    def reject_null(cls, value: str | None) -> str:
        if value is None:
            raise PydanticCustomError("null_not_allowed", "invalid")
        return value

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        try:
            clean_phone(value)
        except PatientFieldError as exc:
            raise PydanticCustomError(exc.code, "invalid") from None
        return value


class PatientStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "inactive"]


class PatientResponse(BaseModel):
    id: UUID
    patient_number: int
    display_id: str
    full_name: str
    phone: str
    date_of_birth: date | None
    status: Literal["active", "inactive"]
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
        status=_status(item.status),
        created_at=item.created_at,
    )


def _status(value: str) -> Literal["active", "inactive"]:
    if value == "active":
        return "active"
    if value == "inactive":
        return "inactive"
    raise RuntimeError("patient status is not active or inactive")


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
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    q: str | None = None,
    status: Literal["active", "inactive"] | None = None,
) -> PatientListResponse:
    found = list_patients(session, user.clinic.id, q, page, page_size, status)
    return PatientListResponse(
        items=[_response(item) for item in found.items],
        total=found.total,
        page=found.page,
        page_size=found.page_size,
    )


@router.get("/patients/{patient_id}")
def get_patient_by_id(
    patient_id: UUID,
    user: Annotated[CurrentUser, Depends(can_use_patients)],
    session: SessionDep,
) -> PatientResponse:
    try:
        found = get_patient(session, user.clinic.id, patient_id)
    except PatientNotFoundError:
        raise HTTPException(status_code=404) from None
    return _response(found)


@router.patch("/patients/{patient_id}")
def patch_patient(
    patient_id: UUID,
    body: PatientUpdate,
    user: Annotated[CurrentUser, Depends(can_use_patients)],
    session: SessionDep,
) -> PatientResponse:
    try:
        updated = edit_patient(
            session,
            user.clinic.id,
            user.id,
            patient_id,
            PatientChanges(
                fields=frozenset(body.model_fields_set),
                full_name=body.full_name,
                phone=body.phone,
                date_of_birth=body.date_of_birth,
            ),
        )
    except PatientFieldError as exc:
        raise _field_error(exc) from None
    except PatientNotFoundError:
        raise HTTPException(status_code=404) from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    session.commit()
    return _response(updated)


@router.put("/patients/{patient_id}/status")
def put_patient_status(
    patient_id: UUID,
    body: PatientStatusUpdate,
    user: Annotated[CurrentUser, Depends(can_use_patients)],
    session: SessionDep,
) -> PatientResponse:
    try:
        updated = set_patient_status(session, user.clinic.id, user.id, patient_id, body.status)
    except PatientFieldError as exc:
        raise _field_error(exc) from None
    except PatientNotFoundError:
        raise HTTPException(status_code=404) from None
    session.commit()
    return _response(updated)
