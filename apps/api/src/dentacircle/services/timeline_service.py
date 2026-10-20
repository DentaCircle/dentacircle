"""Write one timeline step, and list a patient's steps newest first."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from dentacircle.domain.timeline import TIMELINE_KINDS, subject_column
from dentacircle.models.timeline_event import TimelineEvent
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.repositories.timeline_repository import TimelineRepository
from dentacircle.services.clinic_day_service import ClinicNotFoundError


class UnknownTimelineKindError(Exception):
    """A kind outside the closed list."""


class TimelineSubjectError(Exception):
    """The subject id does not match the kind."""


@dataclass(frozen=True)
class ActorView:
    id: UUID
    name: str


@dataclass(frozen=True)
class VisitSubject:
    appointment_id: UUID
    type_name: str
    clinician_name: str
    starts_at: datetime


@dataclass(frozen=True)
class CareItemSubject:
    name: str


@dataclass(frozen=True)
class CareSessionSubject:
    care_session_id: UUID
    item_names: tuple[str, ...]


@dataclass(frozen=True)
class FollowUpSubject:
    due_on: date


@dataclass(frozen=True)
class RecallSubject:
    due_on: date
    type_name: str


SubjectView = (
    VisitSubject | CareItemSubject | CareSessionSubject | FollowUpSubject | RecallSubject | None
)


@dataclass(frozen=True)
class TimelineItemView:
    id: UUID
    kind: str
    occurred_at: datetime
    actor: ActorView
    subject: SubjectView


@dataclass(frozen=True)
class TimelinePage:
    items: list[TimelineItemView]
    total: int
    page: int
    page_size: int


def record(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient_id: UUID,
    kind: str,
    *,
    appointment_id: UUID | None = None,
    care_item_id: UUID | None = None,
    care_session_id: UUID | None = None,
    follow_up_id: UUID | None = None,
    recall_id: UUID | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Append one step in the caller's transaction. The row is not updated later."""
    if kind not in TIMELINE_KINDS:
        raise UnknownTimelineKindError
    subjects = {
        "appointment_id": appointment_id,
        "care_item_id": care_item_id,
        "care_session_id": care_session_id,
        "follow_up_id": follow_up_id,
        "recall_id": recall_id,
    }
    _check_subject(kind, subjects)
    moment = occurred_at if occurred_at is not None else datetime.now(UTC)
    TimelineRepository(session, clinic_id).add(
        TimelineEvent(
            id=uuid4(),
            patient_id=patient_id,
            actor_user_id=actor_user_id,
            kind=kind,
            occurred_at=moment,
            appointment_id=appointment_id,
            care_item_id=care_item_id,
            care_session_id=care_session_id,
            follow_up_id=follow_up_id,
            recall_id=recall_id,
        )
    )


def list_timeline(
    session: Session,
    clinic_id: UUID,
    patient_id: UUID,
    page: int,
    page_size: int,
) -> TimelinePage:
    """This clinic's events for the patient, newest first. An unknown patient is an error."""
    # Local import: patient_service records a timeline event, so a top-level import cycles.
    from dentacircle.services.patient_service import PatientNotFoundError

    if PatientRepository(session, clinic_id).get(patient_id) is None:
        raise PatientNotFoundError
    zone = _zone(session, clinic_id)
    repository = TimelineRepository(session, clinic_id)
    rows, total = repository.list_for_patient(patient_id, page, page_size)
    loaded = _loaded(repository, rows)
    return TimelinePage(
        items=[_item(row, zone, loaded) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _check_subject(kind: str, subjects: dict[str, UUID | None]) -> None:
    expected = subject_column(kind)
    filled = [name for name, value in subjects.items() if value is not None]
    if expected is None:
        if filled:
            raise TimelineSubjectError
        return
    if filled != [expected]:
        raise TimelineSubjectError


@dataclass(frozen=True)
class _Loaded:
    actors: dict[UUID, str]
    visits: dict[UUID, tuple[str, str, datetime]]
    care_items: dict[UUID, str]
    sessions: dict[UUID, tuple[str, ...]]
    follow_ups: dict[UUID, date]
    recalls: dict[UUID, tuple[date, str]]


def _loaded(repository: TimelineRepository, rows: list[TimelineEvent]) -> _Loaded:
    return _Loaded(
        actors=repository.actor_names({row.actor_user_id for row in rows}),
        visits=repository.visits(
            {row.appointment_id for row in rows if row.appointment_id is not None}
        ),
        care_items=repository.care_item_names(
            {row.care_item_id for row in rows if row.care_item_id is not None}
        ),
        sessions=repository.session_item_names(
            {row.care_session_id for row in rows if row.care_session_id is not None}
        ),
        follow_ups=repository.follow_up_due_on(
            {row.follow_up_id for row in rows if row.follow_up_id is not None}
        ),
        recalls=repository.recalls({row.recall_id for row in rows if row.recall_id is not None}),
    )


def _item(row: TimelineEvent, zone: ZoneInfo, loaded: _Loaded) -> TimelineItemView:
    name = loaded.actors.get(row.actor_user_id)
    if name is None:
        raise RuntimeError("timeline event points at a missing actor")
    return TimelineItemView(
        id=row.id,
        kind=row.kind,
        occurred_at=row.occurred_at.astimezone(zone),
        actor=ActorView(id=row.actor_user_id, name=name),
        subject=_subject(row, zone, loaded),
    )


def _subject(row: TimelineEvent, zone: ZoneInfo, loaded: _Loaded) -> SubjectView:
    if row.kind == "patient_registered":
        return None
    if row.appointment_id is not None:
        found = loaded.visits.get(row.appointment_id)
        if found is None:
            raise RuntimeError("timeline event points at a missing visit")
        type_name, clinician_name, starts_at = found
        return VisitSubject(
            appointment_id=row.appointment_id,
            type_name=type_name,
            clinician_name=clinician_name,
            starts_at=starts_at.astimezone(zone),
        )
    if row.care_item_id is not None:
        name = loaded.care_items.get(row.care_item_id)
        if name is None:
            raise RuntimeError("timeline event points at a missing care item")
        return CareItemSubject(name=name)
    if row.care_session_id is not None:
        names = loaded.sessions.get(row.care_session_id)
        if names is None:
            raise RuntimeError("timeline event points at a missing care session")
        return CareSessionSubject(care_session_id=row.care_session_id, item_names=names)
    if row.follow_up_id is not None:
        due_on = loaded.follow_ups.get(row.follow_up_id)
        if due_on is None:
            raise RuntimeError("timeline event points at a missing follow-up")
        return FollowUpSubject(due_on=due_on)
    if row.recall_id is not None:
        recall = loaded.recalls.get(row.recall_id)
        if recall is None:
            raise RuntimeError("timeline event points at a missing recall")
        due_on, type_name = recall
        return RecallSubject(due_on=due_on, type_name=type_name)
    raise RuntimeError("timeline event has no subject")


def _zone(session: Session, clinic_id: UUID) -> ZoneInfo:
    clinic = ClinicDayRepository(session, clinic_id).get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    try:
        return ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        raise ClinicNotFoundError from None
