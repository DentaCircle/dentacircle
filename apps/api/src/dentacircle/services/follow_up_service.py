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
    CANCELLABLE_STATUSES,
    CONTACTABLE_STATUSES,
    DUE_QUEUE_STATUSES,
    OPEN_FOLLOW_UP_STATUSES,
    due_date,
    due_on_problem,
    follow_up_timing,
    needs_follow_up,
)
from dentacircle.domain.patient import display_id
from dentacircle.domain.timeline import FOLLOW_UP_MOVE_KIND
from dentacircle.models.appointment import Appointment
from dentacircle.models.follow_up import FollowUp
from dentacircle.models.patient import Patient
from dentacircle.repositories.care_repository import CareRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.follow_up_repository import FollowUpRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.audit_service import record
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.patient_lock import lock_patient
from dentacircle.services.patient_service import PatientNotFoundError
from dentacircle.services.timeline_service import record as record_timeline

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
    """Lock the patient, close this visit's booked follow-up, then create or retarget.

    The visit row is already locked by the caller. The patient lock is taken after that
    one, and the follow-up lock after the patient. Closing first frees the open slot
    before a new row is written. A clinician date is used as given. Without one, the
    seven-day rule still applies, and only when the patient is active with an open item.
    An inactive patient still has the booked follow-up closed, and gets no new row.
    """
    patient = lock_patient(session, clinic_id, appointment.patient_id)
    complete_booked_follow_up(
        session, clinic_id, actor_user_id, appointment, occurred_at=completed_at
    )
    if due_on is not None:
        if patient.status != "active":
            return
        _save_dated_follow_up(
            session,
            clinic_id,
            actor_user_id,
            patient.id,
            appointment.id,
            due_on,
            occurred_at=completed_at,
        )
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
        occurred_at=completed_at,
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
    occurred_at: datetime | None = None,
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
        record_timeline(
            session,
            clinic_id,
            actor_user_id,
            patient_id,
            "follow_up_created",
            follow_up_id=follow_up.id,
            occurred_at=occurred_at,
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
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        patient_id,
        "follow_up_updated",
        follow_up_id=existing.id,
        occurred_at=occurred_at,
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
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        patient.id,
        "follow_up_created",
        follow_up_id=follow_up.id,
        occurred_at=now,
    )
    try:
        session.flush()
    except IntegrityError as exc:
        if _is_open_conflict(exc):
            raise FollowUpOpenError from None
        raise
    session.refresh(follow_up)
    return _view(follow_up)


def place_follow_up_for_ready_lab(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient: Patient,
    today: date,
    occurred_at: datetime,
) -> None:
    """Create or pull forward the open follow-up when lab work becomes ready.

    The caller has already locked the patient, then the lab row. This locks the
    follow-up after those two. An inactive patient is left unchanged. A booked
    follow-up, and one already due, are left unchanged. Collecting or cancelling
    lab work does not call this.
    """
    if patient.status != "active":
        return
    repository = FollowUpRepository(session, clinic_id)
    existing = repository.get_open(patient.id, lock=True)
    if existing is None:
        follow_up = FollowUp(
            id=uuid4(),
            patient_id=patient.id,
            appointment_id=None,
            status="scheduled",
            due_on=today,
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
        record_timeline(
            session,
            clinic_id,
            actor_user_id,
            patient.id,
            "follow_up_created",
            follow_up_id=follow_up.id,
            occurred_at=occurred_at,
        )
        return
    if existing.status == "booked" or existing.due_on <= today:
        return
    existing.due_on = today
    record(
        session,
        clinic_id,
        actor_user_id,
        "follow_up",
        existing.id,
        "update",
        changed_fields=["due_on"],
    )
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        patient.id,
        "follow_up_updated",
        follow_up_id=existing.id,
        occurred_at=occurred_at,
    )


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


def complete_booked_follow_up(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment: Appointment,
    *,
    occurred_at: datetime | None = None,
) -> None:
    """Close the booked follow-up for this visit. The patient row is already locked.

    The caller holds the visit lock, then the patient lock. This takes the follow-up
    lock next. A visit that is not the booked visit does nothing.
    """
    _move_booked_follow_up(
        session, clinic_id, actor_user_id, appointment.id, "completed", occurred_at=occurred_at
    )


def release_booked_follow_up(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment: Appointment,
) -> None:
    """Return the booked follow-up for this visit to contacted. The visit is already locked.

    The patient lock is taken here, then the follow-up. `due_on` and the visit id stay.
    A visit that is not the booked visit does nothing.
    """
    lock_patient(session, clinic_id, appointment.patient_id)
    _move_booked_follow_up(session, clinic_id, actor_user_id, appointment.id, "contacted")


def cancel_follow_up(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    follow_up_id: UUID,
) -> None:
    """Lock the patient, then the follow-up, and cancel an open row. The visit stays."""
    row, patient = _locked_row(session, clinic_id, follow_up_id)
    if patient.status != "active":
        raise PatientInactiveError
    if row.status not in CANCELLABLE_STATUSES:
        raise FollowUpInvalidStatusError
    row.status = "cancelled"
    record(
        session,
        clinic_id,
        actor_user_id,
        "follow_up",
        row.id,
        "status_change",
        changed_fields=["status"],
    )
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        row.patient_id,
        "follow_up_cancelled",
        follow_up_id=row.id,
    )


def _move_booked_follow_up(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment_id: UUID,
    status: str,
    *,
    occurred_at: datetime | None = None,
) -> None:
    """Lock the booked follow-up for this visit and set its status. Flush before any insert."""
    row = FollowUpRepository(session, clinic_id).get_booked_for_appointment(
        appointment_id, lock=True
    )
    if row is None:
        return
    row.status = status
    record(
        session,
        clinic_id,
        actor_user_id,
        "follow_up",
        row.id,
        "status_change",
        changed_fields=["status"],
    )
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        row.patient_id,
        FOLLOW_UP_MOVE_KIND[status],
        follow_up_id=row.id,
        occurred_at=occurred_at,
    )
    session.flush()


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
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        row.patient_id,
        "follow_up_contacted",
        follow_up_id=row.id,
        occurred_at=now,
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
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        row.patient_id,
        "follow_up_booked",
        follow_up_id=row.id,
        occurred_at=now,
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
