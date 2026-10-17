"""Create or update the one open follow-up when a visit is completed."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from dentacircle.domain.follow_up import due_date, needs_follow_up
from dentacircle.models.appointment import Appointment
from dentacircle.models.follow_up import FollowUp
from dentacircle.repositories.care_repository import CareRepository
from dentacircle.repositories.follow_up_repository import FollowUpRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.audit_service import record
from dentacircle.services.patient_service import PatientNotFoundError


@dataclass(frozen=True)
class FollowUpView:
    id: UUID
    patient_id: UUID
    appointment_id: UUID
    status: str
    due_on: date
    created_at: datetime


def record_incomplete_care(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment: Appointment,
    zone: ZoneInfo,
    completed_at: datetime,
) -> None:
    """Lock the patient, then create or retarget the open follow-up.

    The visit row is already locked by the caller. This lock is taken after that one.
    """
    patient = PatientRepository(session, clinic_id).get(appointment.patient_id, lock=True)
    if patient is None:
        raise RuntimeError("visit points at a missing patient")
    statuses = CareRepository(session, clinic_id).list_item_statuses(patient.id)
    if not needs_follow_up(patient.status, statuses):
        return
    repository = FollowUpRepository(session, clinic_id)
    existing = repository.get_open(patient.id)
    if existing is None:
        follow_up = FollowUp(
            id=uuid4(),
            patient_id=patient.id,
            appointment_id=appointment.id,
            status="scheduled",
            due_on=due_date(completed_at, zone),
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
    existing.appointment_id = appointment.id
    record(
        session,
        clinic_id,
        actor_user_id,
        "follow_up",
        existing.id,
        "update",
        changed_fields=["appointment_id"],
    )


def get_open_follow_up(session: Session, clinic_id: UUID, patient_id: UUID) -> FollowUpView | None:
    """The patient's open follow-up, or none. A missing patient is not an empty result."""
    if PatientRepository(session, clinic_id).get(patient_id) is None:
        raise PatientNotFoundError
    row = FollowUpRepository(session, clinic_id).get_open(patient_id)
    if row is None:
        return None
    return FollowUpView(
        id=row.id,
        patient_id=row.patient_id,
        appointment_id=row.appointment_id,
        status=row.status,
        due_on=row.due_on,
        created_at=row.created_at,
    )
