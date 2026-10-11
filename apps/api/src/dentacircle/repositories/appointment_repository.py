"""Reads and writes for one clinic's appointments. Every method takes that clinic."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.domain.appointment import NON_BLOCKING_STATUSES
from dentacircle.models.appointment import Appointment


class AppointmentRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, appointment: Appointment) -> None:
        appointment.clinic_id = self._clinic_id
        self._session.add(appointment)

    def busy_spans(
        self,
        *,
        span_start: datetime,
        span_end: datetime,
        clinician_user_id: UUID | None = None,
        patient_id: UUID | None = None,
    ) -> list[tuple[datetime, datetime]]:
        """Blocking visits that overlap [span_start, span_end). Half-open, like the constraint."""
        if clinician_user_id is None and patient_id is None:
            raise ValueError("a clinician or a patient is required")
        statement = scoped_select(Appointment, self._clinic_id).where(
            Appointment.status.notin_(NON_BLOCKING_STATUSES),
            Appointment.starts_at < span_end,
            Appointment.ends_at > span_start,
        )
        if clinician_user_id is not None:
            statement = statement.where(Appointment.clinician_user_id == clinician_user_id)
        if patient_id is not None:
            statement = statement.where(Appointment.patient_id == patient_id)
        statement = statement.order_by(Appointment.starts_at, Appointment.id)
        rows = self._session.scalars(statement)
        return [(row.starts_at, row.ends_at) for row in rows]

    def upcoming_for_patient(
        self, patient_id: UUID, now: datetime, limit: int
    ) -> list[Appointment]:
        """Blocking visits that end after now, soonest first."""
        statement = (
            scoped_select(Appointment, self._clinic_id)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.status.notin_(NON_BLOCKING_STATUSES),
                Appointment.ends_at > now,
            )
            .order_by(Appointment.starts_at, Appointment.id)
            .limit(limit)
        )
        return list(self._session.scalars(statement))
