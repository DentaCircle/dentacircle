"""Read and record the care session for one visit."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.care_session import (
    CARE_SESSION_READ_ROLES,
    CARE_SESSION_WRITE_ROLES,
    MAX_SESSION_ITEMS,
    SessionFieldError,
)
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.care_session_service import (
    CareSessionNotFoundError,
    CareSessionView,
    InvalidVisitStatusError,
    ItemChangedError,
    SessionExistsError,
    SessionItemView,
    UnknownItemError,
    get_session,
    record_session,
)

router = APIRouter()

can_read = require_roles(*CARE_SESSION_READ_ROLES)
can_write = require_roles(*CARE_SESSION_WRITE_ROLES)

SessionResult = Literal["started", "completed"]


class SessionItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    care_item_id: UUID
    status: SessionResult


class RecordBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SessionItemBody] = Field(min_length=1, max_length=MAX_SESSION_ITEMS)


class SessionItemResponse(BaseModel):
    care_item_id: UUID
    name: str
    plan_title: str
    status: SessionResult


class SessionResponse(BaseModel):
    id: UUID
    appointment_id: UUID
    patient_id: UUID
    recorded_by_name: str
    created_at: datetime
    items: list[SessionItemResponse]


class SessionEnvelope(BaseModel):
    session: SessionResponse | None


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
}
_WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
    409: {"model": ErrorResponse, "description": "invalid_status, session_exists, or item_changed"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}


def _visit_for_read(
    appointment_id: UUID,
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
) -> UUID:
    """404 before the body is read, so a missing visit is not a validation error."""
    _missing_visit(session, user, appointment_id)
    return appointment_id


def _visit_for_write(
    appointment_id: UUID,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> UUID:
    _missing_visit(session, user, appointment_id)
    return appointment_id


def _missing_visit(session: SessionDep, user: CurrentUser, appointment_id: UUID) -> None:
    try:
        get_session(session, user.clinic.id, appointment_id)
    except CareSessionNotFoundError:
        raise HTTPException(status_code=404) from None


@router.get("/appointments/{appointment_id}/care-session", responses=_READ_ERRORS)
def get_care_session(
    appointment_id: Annotated[UUID, Depends(_visit_for_read)],
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
) -> SessionEnvelope:
    try:
        found = get_session(session, user.clinic.id, appointment_id)
    except CareSessionNotFoundError:
        raise HTTPException(status_code=404) from None
    if found is None:
        return SessionEnvelope(session=None)
    return SessionEnvelope(session=_session(found))


@router.post(
    "/appointments/{appointment_id}/care-session",
    status_code=201,
    responses=_WRITE_ERRORS,
)
def post_care_session(
    appointment_id: Annotated[UUID, Depends(_visit_for_write)],
    body: RecordBody,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> SessionResponse:
    try:
        recorded = record_session(
            session,
            user.clinic.id,
            user.id,
            appointment_id,
            [(item.care_item_id, item.status) for item in body.items],
        )
    except SessionFieldError as exc:
        raise _field_error(exc) from None
    except CareSessionNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidVisitStatusError:
        raise CodedHttpError(
            409, "invalid_status", "This visit can no longer take a care session."
        ) from None
    except SessionExistsError:
        raise CodedHttpError(
            409, "session_exists", "A care session was already recorded for this visit."
        ) from None
    except UnknownItemError:
        raise _unknown_item() from None
    except ItemChangedError:
        raise CodedHttpError(409, "item_changed", "A care item has already changed.") from None
    session.commit()
    return _session(recorded)


def _field_error(exc: SessionFieldError) -> RequestValidationError:
    return RequestValidationError(
        [{"type": exc.code, "loc": ("body", exc.field), "msg": exc.code, "input": None}]
    )


def _unknown_item() -> RequestValidationError:
    return RequestValidationError(
        [{"type": "unknown_item", "loc": ("body", "items"), "msg": "unknown_item", "input": None}]
    )


def _session(row: CareSessionView) -> SessionResponse:
    return SessionResponse(
        id=row.id,
        appointment_id=row.appointment_id,
        patient_id=row.patient_id,
        recorded_by_name=row.recorded_by_name,
        created_at=row.created_at,
        items=[_item(item) for item in row.items],
    )


def _item(item: SessionItemView) -> SessionItemResponse:
    return SessionItemResponse(
        care_item_id=item.care_item_id,
        name=item.name,
        plan_title=item.plan_title,
        status=_result(item.status),
    )


def _result(value: str) -> SessionResult:
    if value == "started":
        return "started"
    if value == "completed":
        return "completed"
    raise RuntimeError("care session result is not started or completed")
