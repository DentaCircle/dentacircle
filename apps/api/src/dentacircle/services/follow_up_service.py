"""Create or update the one open follow-up when a visit is completed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.domain.follow_up import (
    BOOKABLE_STATUSES,
    CONTACTABLE_STATUSES,
    DUE_QUEUE_STATUSES,
    OPEN_FOLLOW_UP_STATUSES,
    due_date,
    due_on_problem,
    follow_up_timing,
    needs_follow_up,
)
from dentacircle.domain.patient import display_id
from dentacircle.models.appointment import Appointment
from dentacircle.models.follow_up import FollowUp
from dentacircle.models.patient import Patient
from dentacircle.repositories.care_repository import CareRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.follow_up_repository import FollowUpRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.audit_service import record
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.patient_service import PatientNotFoundError

if TYPE_CHECKING:
    from dentacircle.services.appointment_service import AppointmentView


class FollowUpFieldError(Exception):
    """One field failed a rule. `code` is a validation name and carries no submitted value."""

    def __init__(self, field: str, code: str) -> None:
        self.field = field
        self.code = code
        super().__init__(code)


class PatientInactiveError(Exception):
    """A follow-up cannot be created or updated for an inactive patient."""


class FollowUpOpenError(Exception):
    """The patient already has a scheduled, contacted, or booked follow-up."""


class FollowUpNotFoundError(Exception):
    """No follow-up with this id in the clinic."""


class FollowUpInvalidStatusError(Exception):
    """The follow-up cannot take this status."""


@dataclass(frozen=True)
class FollowUpView:
    id: UUID
    patient_id: UUID
    appointment_id: UUID | None
    status: str
    due_on: date
    created_at: datetime


@dataclass(frozen=True)
class FollowUpPatientView:
    id: UUID
    display_id: str
    full_name: str
    phone: str


@dataclass(frozen=True)
class FollowUpQueueItemView:
    id: UUID
    status: str
    due_on: date
    timing: str
    patient: FollowUpPatientView


@dataclass(frozen=True)
class FollowUpQueuePage:
    items: list[FollowUpQueueItemView]
    total: int
    page: int
    page_size: int


def record_incomplete_care(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment: Appointment,
    zone: ZoneInfo,
    completed_at: datetime,
    due_on: date | None = None,
) -> None:
    """Lock the patient, then create or retarget the open follow-up.

    The visit row is already locked by the caller. This lock is taken after that one.
    A clinician date is used as given. Without one, the seven-day rule still applies,
    and only when the patient is active with an open care item.
    """
    patient = PatientRepository(session, clinic_id).get(appointment.patient_id, lock=True)
    if patient is None:
        raise RuntimeError("visit points at a missing patient")
    if due_on is not None:
        if patient.status != "active":
            return
        _save_dated_follow_up(session, clinic_id, actor_user_id, patient.id, appointment.id, due_on)
        return
    statuses = CareRepository(session, clinic_id).list_item_statuses(patient.id)
    if not needs_follow_up(patient.status, statuses):
        return
    _save_dated_follow_up(
        session,
        clinic_id,
        actor_user_id,
        patient.id,
        appointment.id,
        due_date(completed_at, zone),
        replace_due_on=False,
    )


def _save_dated_follow_up(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient_id: UUID,
    appointment_id: UUID,
    due_on: date,
    *,
    replace_due_on: bool = True,
) -> None:
    repository = FollowUpRepository(session, clinic_id)
    existing = repository.get_open(patient_id)
    if existing is None:
        follow_up = FollowUp(
            id=uuid4(),
            patient_id=patient_id,
            appointment_id=appointment_id,
            status="scheduled",
            due_on=due_on,
        )
        repository.add(follow_up)
        record(
            session,
            clinic_id,
            actor_user_id,
            "follow_up",
            follow_up.id,
            "create",
            changed_fields=[],
        )
        return
    existing.appointment_id = appointment_id
    changed = ["appointment_id"]
    if replace_due_on:
        existing.due_on = due_on
        changed.append("due_on")
    record(
        session,
        clinic_id,
        actor_user_id,
        "follow_up",
        existing.id,
        "update",
        changed_fields=changed,
    )


def create_manual_follow_up(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient_id: UUID,
    due_on: date,
    now: datetime,
) -> FollowUpView:
    """Lock the patient, then create one scheduled follow-up with no visit."""
    zone = _zone(session, clinic_id)
    patient = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if patient is None:
        raise PatientNotFoundError
    problem = due_on_problem(due_on, zone, now)
    if problem is not None:
        raise FollowUpFieldError("due_on", problem)
    if patient.status != "active":
        raise PatientInactiveError
    repository = FollowUpRepository(session, clinic_id)
    if repository.get_open(patient.id) is not None:
        raise FollowUpOpenError
    follow_up = FollowUp(
        id=uuid4(),
        patient_id=patient.id,
        appointment_id=None,
        status="scheduled",
        due_on=due_on,
    )
    repository.add(follow_up)
    record(
        session,
        clinic_id,
        actor_user_id,
        "follow_up",
        follow_up.id,
        "create",
        changed_fields=[],
    )
    try:
        session.flush()
    except IntegrityError as exc:
        if _is_open_conflict(exc):
            raise FollowUpOpenError from None
        raise
    session.refresh(follow_up)
    return _view(follow_up)


def get_open_follow_up(session: Session, clinic_id: UUID, patient_id: UUID) -> FollowUpView | None:
    """The patient's open follow-up, or none. A missing patient is not an empty result."""
    if PatientRepository(session, clinic_id).get(patient_id) is None:
        raise PatientNotFoundError
    row = FollowUpRepository(session, clinic_id).get_open(patient_id)
    if row is None:
        return None
    return _view(row)


def list_follow_ups(
    session: Session,
    clinic_id: UUID,
    view: str,
    page: int,
    page_size: int,
    now: datetime,
) -> FollowUpQueuePage:
    """Open follow-ups for this clinic, with timing calculated from clinic-local today."""
    today = now.astimezone(_zone(session, clinic_id)).date()
    if view == "due":
        statuses: frozenset[str] = DUE_QUEUE_STATUSES
        due_on_on_or_before: date | None = today
    else:
        statuses = OPEN_FOLLOW_UP_STATUSES
        due_on_on_or_before = None
    rows, total = FollowUpRepository(session, clinic_id).list_queue(
        statuses,
        page,
        page_size,
        due_on_on_or_before=due_on_on_or_before,
    )
    return FollowUpQueuePage(
        items=[_queue_item(follow_up, patient, today) for follow_up, patient in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def follow_up_in_clinic(session: Session, clinic_id: UUID, follow_up_id: UUID) -> None:
    """Raise if this clinic has no follow-up with this id."""
    if FollowUpRepository(session, clinic_id).get(follow_up_id) is None:
        raise FollowUpNotFoundError


def mark_contacted(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    follow_up_id: UUID,
    now: datetime,
) -> FollowUpQueueItemView:
    """Lock the patient, then the follow-up, and move scheduled to contacted."""
    row, patient = _locked_row(session, clinic_id, follow_up_id)
    if patient.status != "active":
        raise PatientInactiveError
    if row.status not in CONTACTABLE_STATUSES:
        raise FollowUpInvalidStatusError
    row.status = "contacted"
    record(
        session,
        clinic_id,
        actor_user_id,
        "follow_up",
        row.id,
        "status_change",
        changed_fields=["status"],
    )
    today = now.astimezone(_zone(session, clinic_id)).date()
    return _queue_item(row, patient, today)


def book_follow_up(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    follow_up_id: UUID,
    clinician_id: UUID,
    appointment_type_id: UUID,
    starts_at: datetime,
    now: datetime,
) -> AppointmentView:
    """Lock the patient, then the follow-up, book a visit, and mark the row booked."""
    from dentacircle.services.appointment_service import book_appointment

    row, patient = _locked_row(session, clinic_id, follow_up_id)
    if patient.status != "active":
        raise PatientInactiveError
    if row.status not in BOOKABLE_STATUSES:
        raise FollowUpInvalidStatusError
    appointment = book_appointment(
        session,
        clinic_id,
        actor_user_id,
        patient.id,
        clinician_id,
        appointment_type_id,
        starts_at,
        now,
    )
    row.status = "booked"
    row.booked_appointment_id = appointment.id
    record(
        session,
        clinic_id,
        actor_user_id,
        "follow_up",
        row.id,
        "status_change",
        changed_fields=["status", "booked_appointment_id"],
    )
    return appointment


def _locked_row(session: Session, clinic_id: UUID, follow_up_id: UUID) -> tuple[FollowUp, Patient]:
    """Patient row first, then the follow-up, the same lock order S2.2 uses.

    The first read is the patient id only, so the session does not cache a stale
    follow-up row that would hide a concurrent status change.
    """
    patient_id = session.scalar(
        select(FollowUp.patient_id).where(
            FollowUp.clinic_id == clinic_id, FollowUp.id == follow_up_id
        )
    )
    if patient_id is None:
        raise FollowUpNotFoundError
    patient = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if patient is None:
        raise RuntimeError("follow-up points at a missing patient")
    row = FollowUpRepository(session, clinic_id).get(follow_up_id, lock=True)
    if row is None:
        raise FollowUpNotFoundError
    return row, patient


def _view(row: FollowUp) -> FollowUpView:
    return FollowUpView(
        id=row.id,
        patient_id=row.patient_id,
        appointment_id=row.appointment_id,
        status=row.status,
        due_on=row.due_on,
        created_at=row.created_at,
    )


def _queue_item(row: FollowUp, patient: Patient, today: date) -> FollowUpQueueItemView:
    return FollowUpQueueItemView(
        id=row.id,
        status=row.status,
        due_on=row.due_on,
        timing=follow_up_timing(row.due_on, today),
        patient=FollowUpPatientView(
            id=patient.id,
            display_id=display_id(patient.patient_number),
            full_name=patient.full_name,
            phone=patient.phone,
        ),
    )


def _zone(session: Session, clinic_id: UUID) -> ZoneInfo:
    clinic = ClinicDayRepository(session, clinic_id).get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    try:
        return ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        raise ClinicNotFoundError from None


def _is_open_conflict(exc: IntegrityError) -> bool:
    origin = exc.orig
    if not isinstance(origin, UniqueViolation) or origin.diag.constraint_name is None:
        return False
    return origin.diag.constraint_name == "uq_follow_up_open_patient"
