"""Reads and writes for one clinic's documents. Every query filters by that clinic."""

from datetime import date, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.document import Document
from dentacircle.models.follow_up import FollowUp


class DocumentRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, document: Document) -> None:
        document.clinic_id = self._clinic_id
        self._session.add(document)

    def get_for_patient(self, patient_id: UUID, document_id: UUID) -> Document | None:
        """The document only when it belongs to this patient in this clinic."""
        statement = scoped_select(Document, self._clinic_id).where(
            Document.patient_id == patient_id, Document.id == document_id
        )
        return cast(Document | None, self._session.scalar(statement))

    def list_for_patient(
        self,
        patient_id: UUID,
        page: int,
        page_size: int,
        *,
        appointment_id: UUID | None = None,
        follow_up_id: UUID | None = None,
    ) -> tuple[list[Document], int]:
        """Newest first: created_at, then id. A filter keeps only rows with that link."""
        where = [Document.clinic_id == self._clinic_id, Document.patient_id == patient_id]
        if appointment_id is not None:
            where.append(Document.appointment_id == appointment_id)
        if follow_up_id is not None:
            where.append(Document.follow_up_id == follow_up_id)
        total = self._session.scalar(select(func.count()).select_from(Document).where(*where))
        statement = (
            scoped_select(Document, self._clinic_id)
            .where(*where[1:])
            .order_by(Document.created_at.desc(), Document.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self._session.scalars(statement)), int(total or 0)

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

    def follow_up_links(self, follow_up_ids: set[UUID]) -> dict[UUID, date]:
        """Current due date, read live, for this clinic only."""
        if not follow_up_ids:
            return {}
        rows = self._session.execute(
            select(FollowUp.id, FollowUp.due_on).where(
                FollowUp.clinic_id == self._clinic_id,
                FollowUp.id.in_(follow_up_ids),
            )
        )
        return {follow_up_id: due_on for follow_up_id, due_on in rows}

    def uploader_names(self, user_ids: set[UUID]) -> dict[UUID, str]:
        """Names for these users, including deactivated ones."""
        if not user_ids:
            return {}
        rows = self._session.scalars(
            scoped_select(AppUser, self._clinic_id).where(AppUser.id.in_(user_ids))
        )
        return {row.id: row.full_name for row in rows}
