"""Reads and writes for one clinic's lab work. Every query filters by that clinic."""

from collections.abc import Collection
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.lab_work import LabWork
from dentacircle.models.patient import Patient


class LabWorkRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, lab_work: LabWork) -> None:
        lab_work.clinic_id = self._clinic_id
        self._session.add(lab_work)

    def get(self, lab_work_id: UUID, *, lock: bool = False) -> LabWork | None:
        """This clinic's lab item, or none. Other clinics are not found."""
        statement = scoped_select(LabWork, self._clinic_id).where(LabWork.id == lab_work_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(LabWork | None, self._session.scalar(statement))

    def get_for_patient(self, lab_work_id: UUID, patient_id: UUID) -> LabWork | None:
        """This clinic's lab item for this patient, or none. Status does not matter."""
        statement = scoped_select(LabWork, self._clinic_id).where(
            LabWork.id == lab_work_id,
            LabWork.patient_id == patient_id,
        )
        return cast(LabWork | None, self._session.scalar(statement))

    def get_with_patient(self, lab_work_id: UUID) -> tuple[LabWork, Patient] | None:
        statement = self._joined().where(LabWork.id == lab_work_id)
        found = self._session.execute(statement).one_or_none()
        if found is None:
            return None
        lab_work, patient = found
        return lab_work, patient

    def list_for_patient(
        self, patient_id: UUID, page: int, page_size: int
    ) -> tuple[list[tuple[LabWork, Patient]], int]:
        """Newest first: created_at, then id. Every status."""
        where = [LabWork.clinic_id == self._clinic_id, LabWork.patient_id == patient_id]
        total = self._session.scalar(select(func.count()).select_from(LabWork).where(*where))
        statement = (
            self._joined()
            .where(LabWork.patient_id == patient_id)
            .order_by(LabWork.created_at.desc(), LabWork.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = self._session.execute(statement).all()
        return [(lab_work, patient) for lab_work, patient in rows], int(total or 0)

    def list_for_clinic(
        self,
        statuses: Collection[str],
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[LabWork, Patient]], int]:
        """Expected date ascending, empty dates last, then the oldest created item."""
        where = [
            LabWork.clinic_id == self._clinic_id,
            LabWork.status.in_(tuple(statuses)),
        ]
        total = self._session.scalar(select(func.count()).select_from(LabWork).where(*where))
        statement = (
            self._joined()
            .where(LabWork.status.in_(tuple(statuses)))
            .order_by(
                LabWork.expected_on.asc().nulls_last(),
                LabWork.created_at.asc(),
                LabWork.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = self._session.execute(statement).all()
        return [(lab_work, patient) for lab_work, patient in rows], int(total or 0)

    def appointment_links(self, appointment_ids: set[UUID]) -> dict[UUID, tuple[datetime, str]]:
        """Start and current type name, read live, for this clinic only."""
        if not appointment_ids:
            return {}
        statement = (
            select(Appointment.id, Appointment.starts_at, AppointmentType.name)
            .join(
                AppointmentType,
                (AppointmentType.id == Appointment.appointment_type_id)
                & (AppointmentType.clinic_id == Appointment.clinic_id),
            )
            .where(
                Appointment.clinic_id == self._clinic_id,
                Appointment.id.in_(appointment_ids),
            )
        )
        found: dict[UUID, tuple[datetime, str]] = {}
        for appointment_id, starts_at, type_name in self._session.execute(statement):
            found[appointment_id] = (starts_at, type_name)
        return found

    def creator_names(self, user_ids: set[UUID]) -> dict[UUID, str]:
        """Names for these users, including deactivated ones."""
        if not user_ids:
            return {}
        rows = self._session.scalars(
            scoped_select(AppUser, self._clinic_id).where(AppUser.id.in_(user_ids))
        )
        return {row.id: row.full_name for row in rows}

    def _joined(self) -> Any:
        return (
            select(LabWork, Patient)
            .join(
                Patient,
                (Patient.id == LabWork.patient_id) & (Patient.clinic_id == LabWork.clinic_id),
            )
            .where(LabWork.clinic_id == self._clinic_id)
        )
