"""Record one care session for a visit, and read it back.

Each item moves through the same locked status method as the manual care route.
The visit status is not changed.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from dentacircle.domain.care import can_move
from dentacircle.domain.care_session import clean_entries, visit_can_take_session
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_plan import CarePlan
from dentacircle.models.care_session import CareSession
from dentacircle.models.care_session_item import CareSessionItem
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.repositories.care_repository import CareRepository
from dentacircle.repositories.care_session_repository import CareSessionRepository
from dentacircle.services.audit_service import record
from dentacircle.services.care_service import move_locked_item
from dentacircle.services.timeline_service import record as record_timeline


class CareSessionNotFoundError(Exception):
    """No visit with this id in the caller's clinic."""


class InvalidVisitStatusError(Exception):
    """This visit is not arrived or in progress."""


class SessionExistsError(Exception):
    """This visit already has a care session."""


class UnknownItemError(Exception):
    """An item is missing, or it is not on a plan of this visit's patient."""


class ItemChangedError(Exception):
    """An item cannot take the requested move. Nothing in the request is saved."""


@dataclass(frozen=True)
class SessionItemView:
    care_item_id: UUID
    name: str
    plan_title: str
    status: str


@dataclass(frozen=True)
class CareSessionView:
    id: UUID
    appointment_id: UUID
    patient_id: UUID
    recorded_by_name: str
    created_at: datetime
    items: list[SessionItemView]


def get_session(session: Session, clinic_id: UUID, appointment_id: UUID) -> CareSessionView | None:
    """The visit's session, or None when none was recorded. Missing visits are an error."""
    if AppointmentRepository(session, clinic_id).get_detail(appointment_id) is None:
        raise CareSessionNotFoundError
    row = CareSessionRepository(session, clinic_id).get_for_appointment(appointment_id)
    if row is None:
        return None
    return _view(session, clinic_id, row)


def record_session(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment_id: UUID,
    entries: list[tuple[UUID, str]],
    *,
    occurred_at: datetime | None = None,
) -> CareSessionView:
    """Lock the visit and each item, then save the session and the item moves together."""
    cleaned = clean_entries(entries)
    appointment = AppointmentRepository(session, clinic_id).get_for_update(appointment_id)
    if appointment is None:
        raise CareSessionNotFoundError
    if not visit_can_take_session(appointment.status):
        raise InvalidVisitStatusError
    repository = CareSessionRepository(session, clinic_id)
    if repository.get_for_appointment(appointment.id) is not None:
        raise SessionExistsError
    locked = _lock_items(session, clinic_id, appointment.patient_id, cleaned)
    for item, _plan, status in locked:
        if not can_move(item.status, status):
            raise ItemChangedError
    stamp = occurred_at if occurred_at is not None else datetime.now(UTC)
    for index, (item, _plan, status) in enumerate(locked):
        move_locked_item(
            session,
            clinic_id,
            actor_user_id,
            item,
            status,
            occurred_at=stamp + timedelta(microseconds=index),
        )
    row = CareSession(
        id=uuid4(),
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        recorded_by_user_id=actor_user_id,
    )
    repository.add(row)
    # One base time for the whole transaction; each line gets its own instant.
    # Read order is then the order the clinician saved.
    for index, (item, _plan, status) in enumerate(locked):
        line = CareSessionItem(
            id=uuid4(),
            care_session_id=row.id,
            care_item_id=item.id,
            status=status,
        )
        line.created_at = stamp + timedelta(microseconds=index)
        repository.add_item(line)
    record(
        session,
        clinic_id,
        actor_user_id,
        "care_session",
        row.id,
        "create",
        changed_fields=[],
    )
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        appointment.patient_id,
        "care_session_recorded",
        care_session_id=row.id,
        occurred_at=stamp + timedelta(microseconds=len(locked)),
    )
    session.flush()
    session.refresh(row)
    return _view_from_locked(session, clinic_id, row, locked)


def _lock_items(
    session: Session,
    clinic_id: UUID,
    patient_id: UUID,
    entries: list[tuple[UUID, str]],
) -> list[tuple[CareItem, CarePlan, str]]:
    """Lock items in id order so two sessions cannot deadlock, then check the patient."""
    care = CareRepository(session, clinic_id)
    by_id: dict[UUID, tuple[CareItem, CarePlan, str]] = {}
    for item_id, status in sorted(entries, key=lambda pair: pair[0]):
        item = care.get_item_for_update(item_id)
        plan = care.get_plan(item.care_plan_id) if item is not None else None
        if item is None or plan is None or plan.patient_id != patient_id:
            raise UnknownItemError
        by_id[item_id] = (item, plan, status)
    return [by_id[item_id] for item_id, _status in entries]


def _view(session: Session, clinic_id: UUID, row: CareSession) -> CareSessionView:
    repository = CareSessionRepository(session, clinic_id)
    items = [
        SessionItemView(
            care_item_id=line.care_item_id,
            name=name,
            plan_title=title,
            status=line.status,
        )
        for line, name, title in repository.list_lines(row.id)
    ]
    return CareSessionView(
        id=row.id,
        appointment_id=row.appointment_id,
        patient_id=row.patient_id,
        recorded_by_name=repository.user_name(row.recorded_by_user_id),
        created_at=row.created_at,
        items=items,
    )


def _view_from_locked(
    session: Session,
    clinic_id: UUID,
    row: CareSession,
    locked: list[tuple[CareItem, CarePlan, str]],
) -> CareSessionView:
    return CareSessionView(
        id=row.id,
        appointment_id=row.appointment_id,
        patient_id=row.patient_id,
        recorded_by_name=CareSessionRepository(session, clinic_id).user_name(
            row.recorded_by_user_id
        ),
        created_at=row.created_at,
        items=[
            SessionItemView(
                care_item_id=item.id,
                name=item.name,
                plan_title=plan.title,
                status=status,
            )
            for item, plan, status in locked
        ],
    )
