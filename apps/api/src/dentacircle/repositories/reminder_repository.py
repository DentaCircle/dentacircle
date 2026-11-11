"""Clinic-scoped reminder persistence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.models.appointment import Appointment
from dentacircle.models.patient import Patient
from dentacircle.models.reminder import Reminder


class ReminderRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self.session = session
        self.clinic_id = clinic_id

    def appointment_id(self, reminder_id: UUID) -> UUID | None:
        return self.session.scalar(
            select(Reminder.appointment_id).where(
                Reminder.clinic_id == self.clinic_id, Reminder.id == reminder_id
            )
        )

    def get(self, reminder_id: UUID, *, lock: bool = False) -> Reminder | None:
        query = select(Reminder).where(
            Reminder.clinic_id == self.clinic_id, Reminder.id == reminder_id
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return self.session.scalars(query).one_or_none()

    def pending_for_appointment(self, appointment_id: UUID) -> Reminder | None:
        return self.session.scalars(
            select(Reminder)
            .where(
                Reminder.clinic_id == self.clinic_id,
                Reminder.appointment_id == appointment_id,
                Reminder.status == "pending",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()

    def add(self, reminder: Reminder) -> None:
        reminder.clinic_id = self.clinic_id
        self.session.add(reminder)

    def list(
        self, now: datetime, due_only: bool, page: int
    ) -> tuple[list[tuple[Reminder, Appointment, Patient]], int]:
        query = (
            select(Reminder, Appointment, Patient)
            .join(
                Appointment,
                (Appointment.id == Reminder.appointment_id)
                & (Appointment.clinic_id == self.clinic_id),
            )
            .join(
                Patient,
                (Patient.id == Appointment.patient_id) & (Patient.clinic_id == self.clinic_id),
            )
            .where(
                Reminder.clinic_id == self.clinic_id,
                Reminder.status == "pending",
                Appointment.status == "scheduled",
                Appointment.starts_at > now,
                Patient.status == "active",
            )
        )
        if due_only:
            query = query.where(Reminder.due_at <= now)
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self.session.execute(
            query.order_by(Reminder.due_at, Reminder.id).offset((page - 1) * 20).limit(20)
        ).all()
        return [(reminder, appointment, patient) for reminder, appointment, patient in rows], total
