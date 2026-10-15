"""Care plans and the services on them."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.care import (
    CARE_READ_ROLES,
    CARE_WRITE_ROLES,
    MAX_LABEL_LENGTH,
    CareFieldError,
)
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.care_service import (
    CareItemView,
    CareNotFoundError,
    CarePlanView,
    InvalidStatusError,
    PatientInactiveError,
    add_item,
    change_item_status,
    create_plan,
    list_plans,
    rename_item,
    rename_plan,
    require_item,
    require_patient,
    require_plan,
)

router = APIRouter()

can_read = require_roles(*CARE_READ_ROLES)
can_write = require_roles(*CARE_WRITE_ROLES)

CareItemStatus = Literal["planned", "started", "completed", "cancelled"]
CareStatusTarget = Literal["started", "completed", "cancelled"]


def _trimmed(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class TitleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value: object) -> object:
        return _trimmed(value)


class NameBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return _trimmed(value)


class StatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CareStatusTarget


class CareItemResponse(BaseModel):
    id: UUID
    name: str
    status: CareItemStatus
    created_at: datetime


class CarePlanResponse(BaseModel):
    id: UUID
    patient_id: UUID
    title: str
    created_at: datetime
    is_open: bool
    items: list[CareItemResponse]


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
    409: {"model": ErrorResponse, "description": "patient_inactive"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_PLAN_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_ITEM_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
    409: {"model": ErrorResponse, "description": "invalid_status or patient_inactive"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_STATUS_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
    409: {"model": ErrorResponse, "description": "invalid_status"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}


def _patient_for_read(
    patient_id: UUID,
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
) -> UUID:
    """404 before the body is read, so a missing patient is not a validation error."""
    _missing_patient(session, user, patient_id)
    return patient_id


def _patient_for_write(
    patient_id: UUID,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> UUID:
    _missing_patient(session, user, patient_id)
    return patient_id


def _plan_for_write(
    plan_id: UUID,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> UUID:
    try:
        require_plan(session, user.clinic.id, plan_id)
    except CareNotFoundError:
        raise HTTPException(status_code=404) from None
    return plan_id


def _item_for_write(
    item_id: UUID,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> UUID:
    try:
        require_item(session, user.clinic.id, item_id)
    except CareNotFoundError:
        raise HTTPException(status_code=404) from None
    return item_id


def _missing_patient(session: SessionDep, user: CurrentUser, patient_id: UUID) -> None:
    try:
        require_patient(session, user.clinic.id, patient_id)
    except CareNotFoundError:
        raise HTTPException(status_code=404) from None


@router.get("/patients/{patient_id}/care-plans", responses=_READ_ERRORS)
def get_care_plans(
    patient_id: Annotated[UUID, Depends(_patient_for_read)],
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
) -> list[CarePlanResponse]:
    try:
        rows = list_plans(session, user.clinic.id, patient_id)
    except CareNotFoundError:
        raise HTTPException(status_code=404) from None
    return [_plan(row) for row in rows]


@router.post("/patients/{patient_id}/care-plans", status_code=201, responses=_CREATE_ERRORS)
def post_care_plan(
    patient_id: Annotated[UUID, Depends(_patient_for_write)],
    body: TitleBody,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> CarePlanResponse:
    try:
        created = create_plan(session, user.clinic.id, user.id, patient_id, body.title)
    except CareFieldError as exc:
        raise _field_error(exc) from None
    except CareNotFoundError:
        raise HTTPException(status_code=404) from None
    except PatientInactiveError:
        raise CodedHttpError(409, "patient_inactive", "This patient is inactive.") from None
    session.commit()
    return _plan(created)


@router.patch("/care-plans/{plan_id}", responses=_PLAN_ERRORS)
def patch_care_plan(
    plan_id: Annotated[UUID, Depends(_plan_for_write)],
    body: TitleBody,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> CarePlanResponse:
    try:
        updated = rename_plan(session, user.clinic.id, user.id, plan_id, body.title)
    except CareFieldError as exc:
        raise _field_error(exc) from None
    except CareNotFoundError:
        raise HTTPException(status_code=404) from None
    session.commit()
    return _plan(updated)


@router.post("/care-plans/{plan_id}/items", status_code=201, responses=_ITEM_ERRORS)
def post_care_item(
    plan_id: Annotated[UUID, Depends(_plan_for_write)],
    body: NameBody,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> CareItemResponse:
    try:
        created = add_item(session, user.clinic.id, user.id, plan_id, body.name)
    except CareFieldError as exc:
        raise _field_error(exc) from None
    except CareNotFoundError:
        raise HTTPException(status_code=404) from None
    except PatientInactiveError:
        raise CodedHttpError(409, "patient_inactive", "This patient is inactive.") from None
    session.commit()
    return _item(created)


@router.patch("/care-items/{item_id}", responses=_ITEM_ERRORS)
def patch_care_item(
    item_id: Annotated[UUID, Depends(_item_for_write)],
    body: NameBody,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> CareItemResponse:
    try:
        updated = rename_item(session, user.clinic.id, user.id, item_id, body.name)
    except CareFieldError as exc:
        raise _field_error(exc) from None
    except CareNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidStatusError:
        raise CodedHttpError(409, "invalid_status", "This care item has already changed.") from None
    session.commit()
    return _item(updated)


@router.post("/care-items/{item_id}/status", responses=_STATUS_ERRORS)
def post_care_item_status(
    item_id: Annotated[UUID, Depends(_item_for_write)],
    body: StatusBody,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> CareItemResponse:
    try:
        updated = change_item_status(session, user.clinic.id, user.id, item_id, body.status)
    except CareNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidStatusError:
        raise CodedHttpError(409, "invalid_status", "This care item has already changed.") from None
    session.commit()
    return _item(updated)


def _field_error(exc: CareFieldError) -> RequestValidationError:
    return RequestValidationError(
        [{"type": exc.code, "loc": ("body", exc.field), "msg": exc.code, "input": None}]
    )


def _plan(plan: CarePlanView) -> CarePlanResponse:
    return CarePlanResponse(
        id=plan.id,
        patient_id=plan.patient_id,
        title=plan.title,
        created_at=plan.created_at,
        is_open=plan.is_open,
        items=[_item(item) for item in plan.items],
    )


def _item(item: CareItemView) -> CareItemResponse:
    return CareItemResponse(
        id=item.id,
        name=item.name,
        status=_status(item.status),
        created_at=item.created_at,
    )


def _status(value: str) -> CareItemStatus:
    if value == "planned":
        return "planned"
    if value == "started":
        return "started"
    if value == "completed":
        return "completed"
    if value == "cancelled":
        return "cancelled"
    raise RuntimeError("care item status is not one of the known statuses")
