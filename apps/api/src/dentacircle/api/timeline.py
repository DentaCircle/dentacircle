"""Read one patient's timeline. Nothing in this module writes a row."""

from datetime import date, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.domain.timeline import TIMELINE_KINDS, TIMELINE_READ_ROLES
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.patient_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PatientNotFoundError,
)
from dentacircle.services.timeline_service import (
    CareItemSubject,
    CareSessionSubject,
    FollowUpSubject,
    RecallSubject,
    TimelineItemView,
    VisitSubject,
    list_timeline,
)

router = APIRouter()

can_read = require_roles(*TIMELINE_READ_ROLES)

TimelineKind = Literal[
    "patient_registered",
    "visit_booked",
    "visit_rescheduled",
    "visit_cancelled",
    "visit_arrived",
    "visit_started",
    "visit_completed",
    "visit_no_show",
    "care_item_added",
    "care_item_started",
    "care_item_completed",
    "care_item_cancelled",
    "care_session_recorded",
    "follow_up_created",
    "follow_up_updated",
    "follow_up_contacted",
    "follow_up_booked",
    "follow_up_completed",
    "follow_up_released",
    "follow_up_cancelled",
    "recall_created",
    "recall_updated",
    "recall_contacted",
    "recall_booked",
    "recall_completed",
    "recall_released",
    "recall_cancelled",
]

MAX_PAGE = (2**63 - 1) // MAX_PAGE_SIZE + 1


class ActorBody(BaseModel):
    id: UUID
    name: str


class VisitSubjectBody(BaseModel):
    appointment_id: UUID
    type_name: str
    clinician_name: str
    starts_at: datetime


class CareItemSubjectBody(BaseModel):
    name: str


class CareSessionSubjectBody(BaseModel):
    care_session_id: UUID
    item_names: list[str]


class FollowUpSubjectBody(BaseModel):
    due_on: date


class RecallSubjectBody(BaseModel):
    due_on: date
    type_name: str


SubjectBody = (
    VisitSubjectBody
    | CareItemSubjectBody
    | CareSessionSubjectBody
    | FollowUpSubjectBody
    | RecallSubjectBody
    | None
)


class TimelineItemBody(BaseModel):
    id: UUID
    kind: TimelineKind
    occurred_at: datetime
    actor: ActorBody
    subject: SubjectBody


class TimelineListResponse(BaseModel):
    items: list[TimelineItemBody]
    total: int
    page: int
    page_size: int


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}


@router.get("/patients/{patient_id}/timeline", responses=_READ_ERRORS)
def get_timeline(
    patient_id: UUID,
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> TimelineListResponse:
    try:
        found = list_timeline(session, user.clinic.id, patient_id, page, page_size)
    except (PatientNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    return TimelineListResponse(
        items=[_item(row) for row in found.items],
        total=found.total,
        page=found.page,
        page_size=found.page_size,
    )


def _item(row: TimelineItemView) -> TimelineItemBody:
    if row.kind not in TIMELINE_KINDS:
        raise RuntimeError("timeline event has an unknown kind")
    return TimelineItemBody(
        id=row.id,
        kind=cast(TimelineKind, row.kind),
        occurred_at=row.occurred_at,
        actor=ActorBody(id=row.actor.id, name=row.actor.name),
        subject=_subject(row),
    )


def _subject(row: TimelineItemView) -> SubjectBody:
    subject = row.subject
    if subject is None:
        return None
    if isinstance(subject, VisitSubject):
        return VisitSubjectBody(
            appointment_id=subject.appointment_id,
            type_name=subject.type_name,
            clinician_name=subject.clinician_name,
            starts_at=subject.starts_at,
        )
    if isinstance(subject, CareItemSubject):
        return CareItemSubjectBody(name=subject.name)
    if isinstance(subject, CareSessionSubject):
        return CareSessionSubjectBody(
            care_session_id=subject.care_session_id,
            item_names=list(subject.item_names),
        )
    if isinstance(subject, FollowUpSubject):
        return FollowUpSubjectBody(due_on=subject.due_on)
    if isinstance(subject, RecallSubject):
        return RecallSubjectBody(due_on=subject.due_on, type_name=subject.type_name)
    raise RuntimeError("timeline event has an unknown subject")
