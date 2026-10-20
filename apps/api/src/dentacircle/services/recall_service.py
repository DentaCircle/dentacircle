"""Create or move the one open recall when a rule-enabled visit is completed."""

from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from dentacircle.domain.recall import MOVABLE_RECALL_STATUSES, recall_due_on
from dentacircle.models.appointment import Appointment
from dentacircle.models.recall import Recall
from dentacircle.repositories.appointment_type_repository import AppointmentTypeRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.repositories.recall_repository import RecallRepository
from dentacircle.services.audit_service import record


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
    patient = PatientRepository(session, clinic_id).get(appointment.patient_id, lock=True)
    if patient is None:
        raise RuntimeError("visit points at a missing patient")
    _move_booked_recall(session, clinic_id, actor_user_id, appointment.id, "completed")
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
    patient = PatientRepository(session, clinic_id).get(appointment.patient_id, lock=True)
    if patient is None:
        raise RuntimeError("visit points at a missing patient")
    _move_booked_recall(session, clinic_id, actor_user_id, appointment.id, "contacted")


def _move_booked_recall(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    appointment_id: UUID,
    status: str,
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
    session.flush()
