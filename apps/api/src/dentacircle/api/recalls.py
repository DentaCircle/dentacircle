"""The recall list, and the contacted, book and cancel actions."""

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_core import PydanticCustomError

from dentacircle.api.appointments import (
    AppointmentResponse,
    AppointmentStatus,
    PartyResponse,
    TypeNameResponse,
)
from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.appointment import APPOINTMENT_STATUSES, AppointmentFieldError
from dentacircle.domain.recall import RECALL_ROLES
from dentacircle.services.appointment_service import (
    AppointmentView,
    PatientBusyError,
    SlotTakenError,
)
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.patient_service import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from dentacircle.services.recall_service import (
    PatientInactiveError,
    RecallInvalidStatusError,
    RecallListItem,
    RecallNotFoundError,
    book_recall,
    cancel_recall,
    get_recall_queue_item,
    list_recalls,
    mark_contacted,
    recall_in_clinic,
)

router = APIRouter()

can_use = require_roles(*RECALL_ROLES)

RecallStatus = Literal["scheduled", "contacted", "booked"]
RecallTiming = Literal["overdue", "due_today", "upcoming"]
RecallViewName = Literal["due", "all"]

MAX_PAGE = (2**63 - 1) // MAX_PAGE_SIZE + 1


class RecallPatientBody(BaseModel):
    id: UUID
    display_id: str
    full_name: str
    phone: str


class RecallTypeBody(BaseModel):
    id: UUID
    name: str


class RecallItemBody(BaseModel):
    id: UUID
    status: RecallStatus
    due_on: date
    timing: RecallTiming
    last_visit_on: date
    recall_type: RecallTypeBody
    patient: RecallPatientBody


class RecallListResponse(BaseModel):
    items: list[RecallItemBody]
    total: int
    page: int
    page_size: int


class RecallBookBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinician_id: UUID
    appointment_type_id: UUID
    starts_at: datetime

    @field_validator("starts_at")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise PydanticCustomError("timezone_naive", "invalid")
        return value


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


_LIST_ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
}
_CONTACTED_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
    409: {"model": ErrorResponse, "description": "invalid_status or patient_inactive"},
}
_CANCEL_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
    409: {"model": ErrorResponse, "description": "invalid_status or patient_inactive"},
}
_BOOK_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
    409: {
        "model": ErrorResponse,
        "description": "invalid_status, slot_taken, patient_busy or patient_inactive",
    },
    422: {"model": ErrorResponse, "description": "validation_error"},
}


@router.get("/recalls", responses=_LIST_ERRORS)
def get_recalls(
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
    view: Annotated[RecallViewName, Query()] = "due",
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> RecallListResponse:
    try:
        found = list_recalls(session, user.clinic.id, view, page, page_size, datetime.now(UTC))
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    return RecallListResponse(
        items=[_item_body(item) for item in found.items],
        total=found.total,
        page=found.page,
        page_size=found.page_size,
    )


@router.get("/recalls/{recall_id}", responses=_READ_ERRORS)
def get_recall(
    recall_id: UUID,
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
) -> RecallItemBody:
    try:
        item = get_recall_queue_item(session, user.clinic.id, recall_id, datetime.now(UTC))
    except RecallNotFoundError:
        raise HTTPException(status_code=404) from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    return _item_body(item)


def _recall_for_write(
    recall_id: UUID,
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
) -> UUID:
    """404 before the body is read, so a missing recall is not a validation error."""
    try:
        recall_in_clinic(session, user.clinic.id, recall_id)
    except RecallNotFoundError:
        raise HTTPException(status_code=404) from None
    return recall_id


@router.post("/recalls/{recall_id}/contacted", responses=_CONTACTED_ERRORS)
def post_contacted(
    recall_id: Annotated[UUID, Depends(_recall_for_write)],
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
) -> RecallItemBody:
    try:
        updated = mark_contacted(session, user.clinic.id, user.id, recall_id, datetime.now(UTC))
    except RecallNotFoundError:
        raise HTTPException(status_code=404) from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    except PatientInactiveError:
        raise CodedHttpError(409, "patient_inactive", "This patient is inactive.") from None
    except RecallInvalidStatusError:
        raise CodedHttpError(409, "invalid_status", "This recall has already changed.") from None
    session.commit()
    return _item_body(updated)


@router.post("/recalls/{recall_id}/book", status_code=201, responses=_BOOK_ERRORS)
def post_book(
    recall_id: UUID,
    body: RecallBookBody,
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
) -> AppointmentResponse:
    try:
        recall_in_clinic(session, user.clinic.id, recall_id)
    except RecallNotFoundError:
        raise HTTPException(status_code=404) from None
    try:
        created = book_recall(
            session,
            user.clinic.id,
            user.id,
            recall_id,
            body.clinician_id,
            body.appointment_type_id,
            body.starts_at,
            datetime.now(UTC),
        )
    except AppointmentFieldError as exc:
        raise _appointment_field_error(exc) from None
    except RecallNotFoundError:
        raise HTTPException(status_code=404) from None
    except ClinicNotFoundError:
        raise HTTPException(status_code=404) from None
    except PatientInactiveError:
        raise CodedHttpError(409, "patient_inactive", "This patient is inactive.") from None
    except RecallInvalidStatusError:
        raise CodedHttpError(409, "invalid_status", "This recall has already changed.") from None
    except SlotTakenError:
        raise CodedHttpError(409, "slot_taken", "That time was just taken.") from None
    except PatientBusyError:
        raise CodedHttpError(
            409, "patient_busy", "That patient already has an appointment then."
        ) from None
    session.commit()
    return _appointment_body(created)


@router.post("/recalls/{recall_id}/cancel", status_code=204, responses=_CANCEL_ERRORS)
def post_cancel(
    recall_id: Annotated[UUID, Depends(_recall_for_write)],
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
) -> Response:
    try:
        cancel_recall(session, user.clinic.id, user.id, recall_id)
    except RecallNotFoundError:
        raise HTTPException(status_code=404) from None
    except PatientInactiveError:
        raise CodedHttpError(409, "patient_inactive", "This patient is inactive.") from None
    except RecallInvalidStatusError:
        raise CodedHttpError(409, "invalid_status", "This recall has already changed.") from None
    session.commit()
    return Response(status_code=204)


def _appointment_field_error(exc: AppointmentFieldError) -> RequestValidationError:
    return RequestValidationError(
        [{"type": exc.code, "loc": ("body", exc.field), "msg": exc.code, "input": None}]
    )


def _appointment_body(item: AppointmentView) -> AppointmentResponse:
    return AppointmentResponse(
        id=item.id,
        patient_id=item.patient_id,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        status=_visit_status(item.status),
        clinician=PartyResponse(id=item.clinician.id, full_name=item.clinician.full_name),
        appointment_type=TypeNameResponse(
            id=item.appointment_type.id, name=item.appointment_type.name
        ),
    )


def _visit_status(value: str) -> AppointmentStatus:
    if value not in APPOINTMENT_STATUSES:
        raise RuntimeError("appointment status is not one of the known statuses")
    return value  # type: ignore[return-value]


def _item_body(item: RecallListItem) -> RecallItemBody:
    return RecallItemBody(
        id=item.id,
        status=_status(item.status),
        due_on=item.due_on,
        timing=_timing(item.timing),
        last_visit_on=item.last_visit_on,
        recall_type=RecallTypeBody(id=item.recall_type.id, name=item.recall_type.name),
        patient=RecallPatientBody(
            id=item.patient.id,
            display_id=item.patient.display_id,
            full_name=item.patient.full_name,
            phone=item.patient.phone,
        ),
    )


def _status(value: str) -> RecallStatus:
    if value not in ("scheduled", "contacted", "booked"):
        raise RuntimeError("recall status is not one of the open statuses")
    return value  # type: ignore[return-value]


def _timing(value: str) -> RecallTiming:
    if value not in ("overdue", "due_today", "upcoming"):
        raise RuntimeError("recall timing is not one of the known timings")
    return value  # type: ignore[return-value]
