"""Reads and writes for one clinic's follow-ups. Every method takes that clinic."""

from collections.abc import Collection
from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.domain.follow_up import OPEN_FOLLOW_UP_STATUSES
from dentacircle.models.follow_up import FollowUp
from dentacircle.models.patient import Patient


class FollowUpRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, follow_up: FollowUp) -> None:
        follow_up.clinic_id = self._clinic_id
        self._session.add(follow_up)

    def get(self, follow_up_id: UUID, *, lock: bool = False) -> FollowUp | None:
        """This clinic's follow-up, or none. Other clinics are not found."""
        statement = scoped_select(FollowUp, self._clinic_id).where(FollowUp.id == follow_up_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self._session.scalars(statement).one_or_none()

    def get_open(self, patient_id: UUID) -> FollowUp | None:
        """The patient's open follow-up in this clinic, if there is one."""
        statement = scoped_select(FollowUp, self._clinic_id).where(
            FollowUp.patient_id == patient_id,
            FollowUp.status.in_(OPEN_FOLLOW_UP_STATUSES),
        )
        return self._session.scalars(statement).one_or_none()

    def list_queue(
        self,
        statuses: Collection[str],
        page: int,
        page_size: int,
        *,
        due_on_on_or_before: date | None = None,
    ) -> tuple[list[tuple[FollowUp, Patient]], int]:
        """Open follow-ups for active patients, oldest due date first, then patient number."""
        statement = (
            select(FollowUp, Patient)
            .join(
                Patient,
                and_(Patient.id == FollowUp.patient_id, Patient.clinic_id == FollowUp.clinic_id),
            )
            .where(
                FollowUp.clinic_id == self._clinic_id,
                FollowUp.status.in_(tuple(statuses)),
                Patient.status == "active",
            )
        )
        if due_on_on_or_before is not None:
            statement = statement.where(FollowUp.due_on <= due_on_on_or_before)
        total = self._session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self._session.execute(
            statement.order_by(FollowUp.due_on, Patient.patient_number)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [(follow_up, patient) for follow_up, patient in rows], int(total or 0)
