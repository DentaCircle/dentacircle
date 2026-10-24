"""Record lab work and list it for a patient or the whole clinic."""

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.lab_work import (
    LAB_WORK_ROLES,
    LAB_WORK_STATUSES,
    MAX_TITLE_LENGTH,
    LabWorkFieldError,
)
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.lab_work_service import (
    AppointmentLinkView,
    InvalidLabStatusError,
    LabWorkNotFoundError,
    LabWorkPage,
    LabWorkPatientInactiveError,
    LabWorkView,
    PatientLinkView,
    change_lab_status,
    create_lab_work,
    get_lab_work,
    list_clinic_lab_work,
    list_patient_lab_work,
)
from dentacircle.services.patient_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PatientNotFoundError,
)

router = APIRouter()

can_use = require_roles(*LAB_WORK_ROLES)

LabStatus = Literal["pending", "ready", "collected", "cancelled"]
LabView = Literal["open", "all"]

MAX_PAGE = (2**63 - 1) // MAX_PAGE_SIZE + 1


def _trimmed(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class CreateLabWorkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    expected_on: date | None = None
    appointment_id: UUID | None = None

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value: object) -> object:
        return _trimmed(value)


class StatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "ready", "collected", "cancelled"]


class ActorBody(BaseModel):
    id: UUID
    name: str


class AppointmentLinkBody(BaseModel):
    id: UUID
    starts_at: datetime
    type_name: str


class PatientLinkBody(BaseModel):
    id: UUID
    display_id: str
    full_name: str
    phone: str


class LabWorkBody(BaseModel):
    id: UUID
    status: LabStatus
    title: str
    expected_on: date | None
    overdue: bool
    appointment: AppointmentLinkBody | None
    patient: PatientLinkBody
    created_at: datetime
    created_by: ActorBody


class LabWorkListResponse(BaseModel):
    items: list[LabWorkBody]
    total: int
    page: int
    page_size: int


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
}
_LIST_ERRORS: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_CREATE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    409: {"model": ErrorResponse, "description": "patient_inactive"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_STATUS_ERRORS: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    409: {"model": ErrorResponse, "description": "invalid_status"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_CLINIC_ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "validation_error"},
}


@router.post(
    "/patients/{patient_id}/lab-work",
    status_code=201,
    responses=_CREATE_ERRORS,
)
def post_lab_work(
    patient_id: UUID,
    body: CreateLabWorkBody,
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
) -> LabWorkBody:
    try:
        created = create_lab_work(
            session,
            user.clinic.id,
            user.id,
            patient_id,
            body.title,
            body.expected_on,
            body.appointment_id,
            datetime.now(UTC),
        )
    except LabWorkFieldError as exc:
        raise _field_error(exc) from None
    except (LabWorkNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    except LabWorkPatientInactiveError:
        raise CodedHttpError(409, "patient_inactive", "This patient is inactive.") from None
    session.commit()
    return _item(created)


@router.get("/patients/{patient_id}/lab-work", responses=_LIST_ERRORS)
def get_patient_lab_work(
    patient_id: UUID,
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> LabWorkListResponse:
    try:
        found = list_patient_lab_work(
            session, user.clinic.id, patient_id, page, page_size, datetime.now(UTC)
        )
    except (PatientNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    return _page(found)


@router.get("/lab-work", responses=_CLINIC_ERRORS)
def get_clinic_lab_work(
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
    view: Annotated[LabView, Query()] = "open",
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> LabWorkListResponse:
    try:
        found = list_clinic_lab_work(
            session, user.clinic.id, view, page, page_size, datetime.now(UTC)
        )
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    return _page(found)


@router.get("/lab-work/{lab_work_id}", responses=_NOT_FOUND)
def get_one_lab_work(
    lab_work_id: UUID,
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
) -> LabWorkBody:
    try:
        found = get_lab_work(session, user.clinic.id, lab_work_id, datetime.now(UTC))
    except (LabWorkNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    return _item(found)


@router.post("/lab-work/{lab_work_id}/status", responses=_STATUS_ERRORS)
def post_lab_work_status(
    lab_work_id: UUID,
    body: StatusBody,
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
) -> LabWorkBody:
    try:
        updated = change_lab_status(
            session, user.clinic.id, user.id, lab_work_id, body.status, datetime.now(UTC)
        )
    except LabWorkNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidLabStatusError:
        raise CodedHttpError(409, "invalid_status", "This lab work has already changed.") from None
    session.commit()
    return _item(updated)


def _field_error(exc: LabWorkFieldError) -> RequestValidationError:
    return RequestValidationError(
        [{"type": exc.code, "loc": ("body", exc.field), "msg": exc.code, "input": None}]
    )


def _page(found: LabWorkPage) -> LabWorkListResponse:
    return LabWorkListResponse(
        items=[_item(row) for row in found.items],
        total=found.total,
        page=found.page,
        page_size=found.page_size,
    )


def _item(row: LabWorkView) -> LabWorkBody:
    if row.status not in LAB_WORK_STATUSES:
        raise RuntimeError("lab work has an unknown status")
    return LabWorkBody(
        id=row.id,
        status=row.status,
        title=row.title,
        expected_on=row.expected_on,
        overdue=row.overdue,
        appointment=_appointment(row.appointment),
        patient=_patient(row.patient),
        created_at=row.created_at,
        created_by=ActorBody(id=row.created_by.id, name=row.created_by.name),
    )


def _appointment(link: AppointmentLinkView | None) -> AppointmentLinkBody | None:
    if link is None:
        return None
    return AppointmentLinkBody(id=link.id, starts_at=link.starts_at, type_name=link.type_name)


def _patient(patient: PatientLinkView) -> PatientLinkBody:
    return PatientLinkBody(
        id=patient.id,
        display_id=patient.display_id,
        full_name=patient.full_name,
        phone=patient.phone,
    )
