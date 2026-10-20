"""Create, move, list and act on the one open recall for a patient."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.domain.patient import display_id
from dentacircle.domain.recall import (
    BOOKABLE_STATUSES,
    CANCELLABLE_STATUSES,
    CONTACTABLE_STATUSES,
    DUE_LIST_STATUSES,
    MOVABLE_RECALL_STATUSES,
    OPEN_RECALL_STATUSES,
    recall_due_on,
    recall_timing,
)
from dentacircle.domain.timeline import RECALL_MOVE_KIND
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.patient import Patient
from dentacircle.models.recall import Recall
from dentacircle.repositories.appointment_type_repository import AppointmentTypeRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.repositories.recall_repository import RecallRepository
from dentacircle.services.audit_service import record
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.patient_lock import lock_patient
from dentacircle.services.timeline_service import record as record_timeline

if TYPE_CHECKING:
    from dentacircle.services.appointment_service import AppointmentView


def record_recall(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment: Appointment,
    zone: ZoneInfo,
    completed_at: datetime,
) -> None:
    """Close this visit's booked recall, then create or move one for an active patient.

    The visit row is already locked. The patient lock is taken here, then the recall.
    A type with no interval writes nothing. An inactive patient still closes a booked
    recall and gets no new row. A booked recall for a different visit is left alone.
    """
    patient = lock_patient(session, clinic_id, appointment.patient_id)
    _move_booked_recall(
        session, clinic_id, actor_user_id, appointment.id, "completed", occurred_at=completed_at
    )
    appointment_type = AppointmentTypeRepository(session, clinic_id).get(
        appointment.appointment_type_id
    )
    if appointment_type is None:
        raise RuntimeError("visit points at a missing appointment type")
    months = appointment_type.recall_after_months
    if months is None or patient.status != "active":
        return
    due_on = recall_due_on(completed_at, zone, months)
    repository = RecallRepository(session, clinic_id)
    existing = repository.get_open(patient.id, lock=True)
    if existing is None:
        recall = Recall(
            id=uuid4(),
            patient_id=patient.id,
            appointment_type_id=appointment_type.id,
            source_appointment_id=appointment.id,
            status="scheduled",
            due_on=due_on,
        )
        repository.add(recall)
        record(
            session,
            clinic_id,
            actor_user_id,
            "recall",
            recall.id,
            "create",
            changed_fields=[],
        )
        record_timeline(
            session,
            clinic_id,
            actor_user_id,
            patient.id,
            "recall_created",
            recall_id=recall.id,
            occurred_at=completed_at,
        )
        return
    if existing.status not in MOVABLE_RECALL_STATUSES:
        return
    existing.appointment_type_id = appointment_type.id
    existing.source_appointment_id = appointment.id
    existing.due_on = due_on
    record(
        session,
        clinic_id,
        actor_user_id,
        "recall",
        existing.id,
        "update",
        changed_fields=["appointment_type_id", "source_appointment_id", "due_on"],
    )
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        patient.id,
        "recall_updated",
        recall_id=existing.id,
        occurred_at=completed_at,
    )


def release_booked_recall(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment: Appointment,
) -> None:
    """Return the booked recall for this visit to contacted. The visit is already locked.

    The patient lock is taken here, then the recall. `due_on` and the visit id stay.
    A visit that is not the booked visit does nothing.
    """
    lock_patient(session, clinic_id, appointment.patient_id)
    _move_booked_recall(session, clinic_id, actor_user_id, appointment.id, "contacted")


def _move_booked_recall(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment_id: UUID,
    status: str,
    *,
    occurred_at: datetime | None = None,
) -> None:
    """Lock the booked recall for this visit and set its status. Flush before any insert."""
    row = RecallRepository(session, clinic_id).get_booked_for_appointment(appointment_id, lock=True)
    if row is None:
        return
    row.status = status
    record(
        session,
        clinic_id,
        actor_user_id,
        "recall",
        row.id,
        "status_change",
        changed_fields=["status"],
    )
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        row.patient_id,
        RECALL_MOVE_KIND[status],
        recall_id=row.id,
        occurred_at=occurred_at,
    )
    session.flush()


class RecallNotFoundError(Exception):
    """No recall with this id in the caller's clinic."""


class RecallInvalidStatusError(Exception):
    """The recall is not in a status this action allows."""


class PatientInactiveError(Exception):
    """The patient is inactive, so the recall cannot be changed."""


@dataclass(frozen=True)
class RecallPatientView:
    id: UUID
    display_id: str
    full_name: str
    phone: str


@dataclass(frozen=True)
class RecallTypeView:
    id: UUID
    name: str


@dataclass(frozen=True)
class RecallListItem:
    id: UUID
    status: str
    due_on: date
    timing: str
    last_visit_on: date
    recall_type: RecallTypeView
    patient: RecallPatientView


@dataclass(frozen=True)
class RecallListPage:
    items: list[RecallListItem]
    total: int
    page: int
    page_size: int


def list_recalls(
    session: Session,
    clinic_id: UUID,
    view: str,
    page: int,
    page_size: int,
    now: datetime,
) -> RecallListPage:
    """Open recalls for this clinic, with timing calculated from clinic-local today."""
    zone = _zone(session, clinic_id)
    today = now.astimezone(zone).date()
    if view == "due":
        statuses = DUE_LIST_STATUSES
        due_on_on_or_before: date | None = today
    else:
        statuses = OPEN_RECALL_STATUSES
        due_on_on_or_before = None
    rows, total = RecallRepository(session, clinic_id).list_queue(
        statuses,
        page,
        page_size,
        due_on_on_or_before=due_on_on_or_before,
    )
    items = [
        _list_item(recall, patient, starts_at, appointment_type, zone, today)
        for recall, patient, starts_at, appointment_type in rows
    ]
    return RecallListPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


def recall_in_clinic(session: Session, clinic_id: UUID, recall_id: UUID) -> None:
    """Raise if this clinic has no recall with this id."""
    if RecallRepository(session, clinic_id).get(recall_id) is None:
        raise RecallNotFoundError


def get_recall_queue_item(
    session: Session,
    clinic_id: UUID,
    recall_id: UUID,
    now: datetime,
) -> RecallListItem:
    """One open recall for the book page. Missing, closed, or inactive patient is not found."""
    recall = RecallRepository(session, clinic_id).get(recall_id)
    if recall is None or recall.status not in OPEN_RECALL_STATUSES:
        raise RecallNotFoundError
    return _require_item(session, clinic_id, recall_id, now)


def mark_contacted(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    recall_id: UUID,
    now: datetime,
) -> RecallListItem:
    """Lock the patient, then the recall, and move scheduled to contacted."""
    row, _patient = _locked_row(session, clinic_id, recall_id)
    if _patient.status != "active":
        raise PatientInactiveError
    if row.status not in CONTACTABLE_STATUSES:
        raise RecallInvalidStatusError
    row.status = "contacted"
    record(
        session,
        clinic_id,
        actor_user_id,
        "recall",
        row.id,
        "status_change",
        changed_fields=["status"],
    )
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        row.patient_id,
        "recall_contacted",
        recall_id=row.id,
        occurred_at=now,
    )
    return _require_item(session, clinic_id, row.id, now)


def book_recall(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    recall_id: UUID,
    clinician_id: UUID,
    appointment_type_id: UUID,
    starts_at: datetime,
    now: datetime,
) -> AppointmentView:
    """Lock the patient, then the recall, book a visit, and mark the row booked."""
    from dentacircle.services.appointment_service import book_appointment

    row, patient = _locked_row(session, clinic_id, recall_id)
    if patient.status != "active":
        raise PatientInactiveError
    if row.status not in BOOKABLE_STATUSES:
        raise RecallInvalidStatusError
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
        "recall",
        row.id,
        "status_change",
        changed_fields=["status", "booked_appointment_id"],
    )
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        row.patient_id,
        "recall_booked",
        recall_id=row.id,
        occurred_at=now,
    )
    return appointment


def cancel_recall(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    recall_id: UUID,
) -> None:
    """Lock the patient, then the recall, and cancel an open row. The visit stays."""
    row, patient = _locked_row(session, clinic_id, recall_id)
    if patient.status != "active":
        raise PatientInactiveError
    if row.status not in CANCELLABLE_STATUSES:
        raise RecallInvalidStatusError
    row.status = "cancelled"
    record(
        session,
        clinic_id,
        actor_user_id,
        "recall",
        row.id,
        "status_change",
        changed_fields=["status"],
    )
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        row.patient_id,
        "recall_cancelled",
        recall_id=row.id,
    )


def _locked_row(session: Session, clinic_id: UUID, recall_id: UUID) -> tuple[Recall, Patient]:
    """Patient row first, then the recall, the same lock order as a follow-up."""
    patient_id = session.scalar(
        select(Recall.patient_id).where(Recall.clinic_id == clinic_id, Recall.id == recall_id)
    )
    if patient_id is None:
        raise RecallNotFoundError
    patient = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if patient is None:
        raise RuntimeError("recall points at a missing patient")
    row = RecallRepository(session, clinic_id).get(recall_id, lock=True)
    if row is None:
        raise RecallNotFoundError
    return row, patient


def _require_item(
    session: Session, clinic_id: UUID, recall_id: UUID, now: datetime
) -> RecallListItem:
    zone = _zone(session, clinic_id)
    found = RecallRepository(session, clinic_id).queue_row(recall_id)
    if found is None:
        raise RecallNotFoundError
    recall, patient, starts_at, appointment_type = found
    today = now.astimezone(zone).date()
    return _list_item(recall, patient, starts_at, appointment_type, zone, today)


def _list_item(
    recall: Recall,
    patient: Patient,
    starts_at: datetime,
    appointment_type: AppointmentType,
    zone: ZoneInfo,
    today: date,
) -> RecallListItem:
    return RecallListItem(
        id=recall.id,
        status=recall.status,
        due_on=recall.due_on,
        timing=recall_timing(recall.due_on, today),
        last_visit_on=starts_at.astimezone(zone).date(),
        recall_type=RecallTypeView(id=appointment_type.id, name=appointment_type.name),
        patient=RecallPatientView(
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
