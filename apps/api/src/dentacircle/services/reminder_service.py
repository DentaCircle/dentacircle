"""Scheduling and resolving reminders under the same locks as visit changes."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from dentacircle.models.appointment import Appointment
from dentacircle.models.patient import Patient
from dentacircle.models.reminder import Reminder
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.repositories.reminder_repository import ReminderRepository
from dentacircle.services.audit_service import record


class ReminderNotFoundError(Exception):
    pass


class ReminderConflictError(Exception):
    pass


class ReminderTimeError(Exception):
    pass


def _lock_visit(
    session: Session, clinic_id: UUID, appointment_id: UUID
) -> tuple[Appointment, Patient]:
    appointments = AppointmentRepository(session, clinic_id)
    patient_id = appointments.patient_id_for_appointment(appointment_id)
    if patient_id is None:
        raise ReminderNotFoundError
    patient = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    visit = appointments.get_for_update(appointment_id)
    if patient is None or visit is None:
        raise ReminderNotFoundError
    return visit, patient


def _eligible(visit: Appointment, patient: Patient, now: datetime) -> bool:
    return patient.status == "active" and visit.status == "scheduled" and visit.starts_at > now


def schedule(
    session: Session,
    clinic_id: UUID,
    actor_id: UUID,
    appointment_id: UUID,
    due_at: datetime | None,
    now: datetime,
) -> Reminder:
    visit, patient = _lock_visit(session, clinic_id, appointment_id)
    if not _eligible(visit, patient, now):
        raise ReminderConflictError
    due = now if due_at is None else due_at
    if due.tzinfo is None or due.utcoffset() is None or due < now or due >= visit.starts_at:
        raise ReminderTimeError
    reminders = ReminderRepository(session, clinic_id)
    if reminders.pending_for_appointment(appointment_id) is not None:
        raise ReminderConflictError
    reminder = Reminder(id=uuid4(), appointment_id=appointment_id, due_at=due, status="pending")
    reminders.add(reminder)
    record(session, clinic_id, actor_id, "reminder", reminder.id, "create")
    session.flush()
    return reminder


def resolve(
    session: Session, clinic_id: UUID, actor_id: UUID, reminder_id: UUID, target: str, now: datetime
) -> None:
    reminders = ReminderRepository(session, clinic_id)
    appointment_id = reminders.appointment_id(reminder_id)
    if appointment_id is None:
        raise ReminderNotFoundError
    visit, patient = _lock_visit(session, clinic_id, appointment_id)
    reminder = reminders.get(reminder_id, lock=True)
    if reminder is None:
        raise ReminderNotFoundError
    if reminder.status != "pending" or (
        target == "completed" and not _eligible(visit, patient, now)
    ):
        raise ReminderConflictError
    _set_status(session, clinic_id, actor_id, reminder, target, now)


def cancel_for_visit(
    session: Session, clinic_id: UUID, actor_id: UUID, appointment_id: UUID, now: datetime
) -> None:
    reminder = ReminderRepository(session, clinic_id).pending_for_appointment(appointment_id)
    if reminder is not None:
        _set_status(session, clinic_id, actor_id, reminder, "cancelled", now)


def _set_status(
    session: Session,
    clinic_id: UUID,
    actor_id: UUID,
    reminder: Reminder,
    target: str,
    now: datetime,
) -> None:
    reminder.status = target
    reminder.resolved_at = now
    record(
        session,
        clinic_id,
        actor_id,
        "reminder",
        reminder.id,
        "status_change",
        changed_fields=["status", "resolved_at"],
    )
    session.flush()
