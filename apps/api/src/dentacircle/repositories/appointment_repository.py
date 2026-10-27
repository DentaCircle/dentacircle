"""Reads and writes for one clinic's appointments. Every method takes that clinic."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.domain.appointment import NON_BLOCKING_STATUSES
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.patient import Patient


class AppointmentRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, appointment: Appointment) -> None:
        appointment.clinic_id = self._clinic_id
        self._session.add(appointment)

    def list_in_range(
        self,
        *,
        range_start: datetime,
        range_end: datetime,
        clinician_user_id: UUID | None = None,
    ) -> list[tuple[Appointment, Patient, AppUser, AppointmentType]]:
        """Visits that overlap [range_start, range_end), except cancelled, soonest first.

        An overlap includes a visit that starts before range_start and ends after it.
        """
        statement = (
            self._joined()
            .where(
                Appointment.status != "cancelled",
                Appointment.ends_at > range_start,
                Appointment.starts_at < range_end,
            )
            .order_by(Appointment.starts_at, Appointment.id)
        )
        if clinician_user_id is not None:
            statement = statement.where(Appointment.clinician_user_id == clinician_user_id)
        rows = self._session.execute(statement).all()
        return [
            (appointment, patient, clinician, appointment_type)
            for appointment, patient, clinician, appointment_type in rows
        ]

    def get_for_patient(self, appointment_id: UUID, patient_id: UUID) -> Appointment | None:
        """This clinic's visit for this patient, or none. Status does not matter."""
        statement = scoped_select(Appointment, self._clinic_id).where(
            Appointment.id == appointment_id,
            Appointment.patient_id == patient_id,
        )
        return self._session.scalars(statement).one_or_none()

    def get_detail(
        self, appointment_id: UUID
    ) -> tuple[Appointment, Patient, AppUser, AppointmentType] | None:
        statement = self._joined().where(Appointment.id == appointment_id)
        row = self._session.execute(statement).one_or_none()
        if row is None:
            return None
        appointment, patient, clinician, appointment_type = row
        return appointment, patient, clinician, appointment_type

    def get_for_update(self, appointment_id: UUID) -> Appointment | None:
        """Lock the row so a cancel and a move of the same visit cannot pass each other."""
        statement = (
            scoped_select(Appointment, self._clinic_id)
            .where(Appointment.id == appointment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self._session.scalars(statement).one_or_none()

    def _joined(self) -> Select[Appointment, Patient, AppUser, AppointmentType]:
        """Appointment plus patient, clinician and type. Every table is this clinic's."""
        return (
            select(Appointment, Patient, AppUser, AppointmentType)
            .join(
                Patient,
                (Patient.id == Appointment.patient_id) & (Patient.clinic_id == self._clinic_id),
            )
            .join(
                AppUser,
                (AppUser.id == Appointment.clinician_user_id)
                & (AppUser.clinic_id == self._clinic_id),
            )
            .join(
                AppointmentType,
                (AppointmentType.id == Appointment.appointment_type_id)
                & (AppointmentType.clinic_id == self._clinic_id),
            )
            .where(
                Appointment.clinic_id == self._clinic_id,
                Patient.clinic_id == self._clinic_id,
                AppUser.clinic_id == self._clinic_id,
                AppointmentType.clinic_id == self._clinic_id,
            )
        )

    def busy_spans(
        self,
        *,
        span_start: datetime,
        span_end: datetime,
        clinician_user_id: UUID | None = None,
        patient_id: UUID | None = None,
        exclude_appointment_id: UUID | None = None,
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
        if exclude_appointment_id is not None:
            statement = statement.where(Appointment.id != exclude_appointment_id)
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
