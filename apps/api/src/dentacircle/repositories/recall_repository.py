"""Reads and writes for one clinic's recalls. Every method takes that clinic."""

from collections.abc import Collection
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.domain.recall import OPEN_RECALL_STATUSES
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.patient import Patient
from dentacircle.models.recall import Recall

QueueRow = tuple[Recall, Patient, datetime, AppointmentType]


class RecallRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, recall: Recall) -> None:
        recall.clinic_id = self._clinic_id
        self._session.add(recall)

    def get(self, recall_id: UUID, *, lock: bool = False) -> Recall | None:
        """This clinic's recall, or none. Other clinics are not found."""
        statement = scoped_select(Recall, self._clinic_id).where(Recall.id == recall_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self._session.scalars(statement).one_or_none()

    def get_open(self, patient_id: UUID, *, lock: bool = False) -> Recall | None:
        """The patient's open recall in this clinic, if there is one."""
        statement = scoped_select(Recall, self._clinic_id).where(
            Recall.patient_id == patient_id,
            Recall.status.in_(OPEN_RECALL_STATUSES),
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self._session.scalars(statement).one_or_none()

    def get_booked_for_appointment(
        self, appointment_id: UUID, *, lock: bool = False
    ) -> Recall | None:
        """The booked recall whose visit is this one, or none."""
        statement = scoped_select(Recall, self._clinic_id).where(
            Recall.booked_appointment_id == appointment_id,
            Recall.status == "booked",
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self._session.scalars(statement).one_or_none()

    def list_queue(
        self,
        statuses: Collection[str],
        page: int,
        page_size: int,
        *,
        due_on_on_or_before: date | None = None,
    ) -> tuple[list[QueueRow], int]:
        """Open recalls for active patients, oldest due date first, then patient number."""
        statement = self._queue_rows().where(Recall.status.in_(tuple(statuses)))
        if due_on_on_or_before is not None:
            statement = statement.where(Recall.due_on <= due_on_on_or_before)
        total = self._session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self._session.execute(
            statement.order_by(Recall.due_on, Patient.patient_number)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [self._queue_row(row) for row in rows], int(total or 0)

    def queue_row(self, recall_id: UUID) -> QueueRow | None:
        """One recall with the patient, source visit and type, or none."""
        found = self._session.execute(
            self._queue_rows().where(Recall.id == recall_id)
        ).one_or_none()
        if found is None:
            return None
        return self._queue_row(found)

    def _queue_rows(self) -> Any:
        return (
            select(Recall, Patient, Appointment.starts_at, AppointmentType)
            .join(
                Patient,
                and_(Patient.id == Recall.patient_id, Patient.clinic_id == Recall.clinic_id),
            )
            .join(
                Appointment,
                and_(
                    Appointment.id == Recall.source_appointment_id,
                    Appointment.clinic_id == Recall.clinic_id,
                ),
            )
            .join(
                AppointmentType,
                and_(
                    AppointmentType.id == Recall.appointment_type_id,
                    AppointmentType.clinic_id == Recall.clinic_id,
                ),
            )
            .where(Recall.clinic_id == self._clinic_id, Patient.status == "active")
        )

    def _queue_row(self, row: Any) -> QueueRow:
        recall, patient, starts_at, appointment_type = row
        return recall, patient, starts_at, appointment_type
