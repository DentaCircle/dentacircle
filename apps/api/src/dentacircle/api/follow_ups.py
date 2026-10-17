"""Read the one open follow-up for a patient."""

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.domain.follow_up import FOLLOW_UP_READ_ROLES
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.follow_up_service import FollowUpView, get_open_follow_up
from dentacircle.services.patient_service import PatientNotFoundError

router = APIRouter()

can_read = require_roles(*FOLLOW_UP_READ_ROLES)

FollowUpStatus = Literal["scheduled", "contacted", "booked"]


class FollowUpBody(BaseModel):
    id: UUID
    patient_id: UUID
    appointment_id: UUID
    status: FollowUpStatus
    due_on: date
    created_at: datetime


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
