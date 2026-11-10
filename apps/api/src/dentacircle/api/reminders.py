"""Staff appointment reminder endpoints."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_core import PydanticCustomError

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.reminder_service import (
    ReminderConflictError,
    ReminderNotFoundError,
    ReminderTimeError,
    list_reminders,
    resolve,
    schedule,
)

router = APIRouter()
can_use = require_roles("receptionist", "clinician", "clinic_admin")


class ScheduleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def require_offset(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise PydanticCustomError("timezone_naive", "invalid")
        return value


class ReminderBody(BaseModel):
    id: UUID
    appointment_id: UUID
    due_at: datetime
    status: str


class ReminderItem(ReminderBody):
    starts_at: datetime
    patient_id: UUID
    patient_name: str


class ReminderList(BaseModel):
    items: list[ReminderItem]
    total: int
    page: int
    page_size: int


@router.post("/appointments/{appointment_id}/reminders", status_code=201)
def post_reminder(
    appointment_id: UUID,
    body: ScheduleBody,
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
) -> ReminderBody:
    try:
        row = schedule(
            session, user.clinic.id, user.id, appointment_id, body.due_at, datetime.now(UTC)
        )
    except ReminderNotFoundError:
        raise HTTPException(status_code=404) from None
    except ReminderConflictError:
        raise CodedHttpError(
            409, "reminder_conflict", "The visit or reminder has changed."
        ) from None
    except ReminderTimeError:
        raise CodedHttpError(422, "invalid_due_at", "Choose a time before the visit.") from None
    session.commit()
    return ReminderBody(
        id=row.id, appointment_id=row.appointment_id, due_at=row.due_at, status=row.status
    )


@router.get("/reminders")
def get_reminders(
    user: Annotated[CurrentUser, Depends(can_use)],
    session: SessionDep,
    view: Literal["due", "pending"] = "due",
    page: Annotated[int, Query(ge=1, le=(2**63 - 1) // 20)] = 1,
) -> ReminderList:
    rows, total = list_reminders(session, user.clinic.id, datetime.now(UTC), view == "due", page)
    return ReminderList(
        items=[
            ReminderItem(
                id=r.id,
                appointment_id=r.appointment_id,
                due_at=r.due_at,
                status=r.status,
                starts_at=a.starts_at,
                patient_id=p.id,
                patient_name=p.full_name,
            )
            for r, a, p in rows
        ],
        total=total,
        page=page,
        page_size=20,
    )


def _resolve(
    reminder_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    target: Literal["completed", "cancelled"],
) -> Response:
    try:
        resolve(session, user.clinic.id, user.id, reminder_id, target, datetime.now(UTC))
    except ReminderNotFoundError:
        raise HTTPException(status_code=404) from None
    except ReminderConflictError:
        raise CodedHttpError(409, "reminder_conflict", "This reminder has changed.") from None
    session.commit()
    return Response(status_code=204)


@router.post("/reminders/{reminder_id}/complete", status_code=204)
def post_complete(
    reminder_id: UUID, user: Annotated[CurrentUser, Depends(can_use)], session: SessionDep
) -> Response:
    return _resolve(reminder_id, user, session, "completed")


@router.post("/reminders/{reminder_id}/cancel", status_code=204)
def post_cancel(
    reminder_id: UUID, user: Annotated[CurrentUser, Depends(can_use)], session: SessionDep
) -> Response:
    return _resolve(reminder_id, user, session, "cancelled")
