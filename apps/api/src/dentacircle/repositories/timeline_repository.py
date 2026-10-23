"""Append and read timeline rows for one clinic. There is no update or delete."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_session_item import CareSessionItem
from dentacircle.models.document import Document
from dentacircle.models.follow_up import FollowUp
from dentacircle.models.recall import Recall
from dentacircle.models.timeline_event import TimelineEvent


class TimelineRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, event: TimelineEvent) -> None:
        event.clinic_id = self._clinic_id
        self._session.add(event)

    def list_for_patient(
        self, patient_id: UUID, page: int, page_size: int
    ) -> tuple[list[TimelineEvent], int]:
        """Newest first: occurred_at, then seq. `seq` keeps one transaction in write order."""
        where = (TimelineEvent.clinic_id == self._clinic_id, TimelineEvent.patient_id == patient_id)
        total = self._session.scalar(select(func.count()).select_from(TimelineEvent).where(*where))
        statement = (
            scoped_select(TimelineEvent, self._clinic_id)
            .where(TimelineEvent.patient_id == patient_id)
            .order_by(TimelineEvent.occurred_at.desc(), TimelineEvent.seq.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self._session.scalars(statement)), int(total or 0)

    def actor_names(self, user_ids: set[UUID]) -> dict[UUID, str]:
        """Names for these users, including deactivated ones."""
        if not user_ids:
            return {}
        rows = self._session.scalars(
            scoped_select(AppUser, self._clinic_id).where(AppUser.id.in_(user_ids))
        )
        return {row.id: row.full_name for row in rows}

    def visits(self, appointment_ids: set[UUID]) -> dict[UUID, tuple[str, str, datetime]]:
        """Type name, clinician name and start, read live."""
        if not appointment_ids:
            return {}
        statement = (
            select(Appointment.id, AppointmentType.name, AppUser.full_name, Appointment.starts_at)
            .join(
                AppointmentType,
                (AppointmentType.id == Appointment.appointment_type_id)
                & (AppointmentType.clinic_id == Appointment.clinic_id),
            )
            .join(
                AppUser,
                (AppUser.id == Appointment.clinician_user_id)
                & (AppUser.clinic_id == Appointment.clinic_id),
            )
            .where(
                Appointment.clinic_id == self._clinic_id,
                Appointment.id.in_(appointment_ids),
            )
        )
        found: dict[UUID, tuple[str, str, datetime]] = {}
        for appointment_id, type_name, clinician_name, starts_at in self._session.execute(
            statement
        ):
            found[appointment_id] = (type_name, clinician_name, starts_at)
        return found

    def care_item_names(self, item_ids: set[UUID]) -> dict[UUID, str]:
        if not item_ids:
            return {}
        rows = self._session.execute(
            select(CareItem.id, CareItem.name).where(
                CareItem.clinic_id == self._clinic_id, CareItem.id.in_(item_ids)
            )
        )
        return {item_id: name for item_id, name in rows}

    def session_item_names(self, session_ids: set[UUID]) -> dict[UUID, tuple[str, ...]]:
        """Current item names on each session, in the order they were saved."""
        if not session_ids:
            return {}
        rows = self._session.execute(
            select(CareSessionItem.care_session_id, CareItem.name)
            .join(
                CareItem,
                (CareItem.id == CareSessionItem.care_item_id)
                & (CareItem.clinic_id == CareSessionItem.clinic_id),
            )
            .where(
                CareSessionItem.clinic_id == self._clinic_id,
                CareSessionItem.care_session_id.in_(session_ids),
            )
            .order_by(CareSessionItem.care_session_id, CareSessionItem.created_at)
        )
        grouped: dict[UUID, list[str]] = {}
        for session_id, name in rows:
            grouped.setdefault(session_id, []).append(name)
        return {session_id: tuple(names) for session_id, names in grouped.items()}

    def follow_up_due_on(self, follow_up_ids: set[UUID]) -> dict[UUID, date]:
        if not follow_up_ids:
            return {}
        rows = self._session.execute(
            select(FollowUp.id, FollowUp.due_on).where(
                FollowUp.clinic_id == self._clinic_id, FollowUp.id.in_(follow_up_ids)
            )
        )
        return {follow_up_id: due_on for follow_up_id, due_on in rows}

    def document_filenames(self, document_ids: set[UUID]) -> dict[UUID, str]:
        """Current filename, read live. The name is not stored on the event."""
        if not document_ids:
            return {}
        rows = self._session.execute(
            select(Document.id, Document.filename).where(
                Document.clinic_id == self._clinic_id,
                Document.id.in_(document_ids),
            )
        )
        return {document_id: filename for document_id, filename in rows}

    def recalls(self, recall_ids: set[UUID]) -> dict[UUID, tuple[date, str]]:
        """Due date and the current type name."""
        if not recall_ids:
            return {}
        statement = (
            select(Recall.id, Recall.due_on, AppointmentType.name)
            .join(
                AppointmentType,
                (AppointmentType.id == Recall.appointment_type_id)
                & (AppointmentType.clinic_id == Recall.clinic_id),
            )
            .where(Recall.clinic_id == self._clinic_id, Recall.id.in_(recall_ids))
        )
        return {
            recall_id: (due_on, type_name)
            for recall_id, due_on, type_name in self._session.execute(statement)
        }
