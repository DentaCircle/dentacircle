"""Reads and writes for one clinic's follow-ups. Every method takes that clinic."""

from uuid import UUID

from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.domain.follow_up import OPEN_FOLLOW_UP_STATUSES
from dentacircle.models.follow_up import FollowUp


class FollowUpRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, follow_up: FollowUp) -> None:
        follow_up.clinic_id = self._clinic_id
        self._session.add(follow_up)

    def get_open(self, patient_id: UUID) -> FollowUp | None:
        """The patient's open follow-up in this clinic, if there is one."""
        statement = scoped_select(FollowUp, self._clinic_id).where(
            FollowUp.patient_id == patient_id,
            FollowUp.status.in_(OPEN_FOLLOW_UP_STATUSES),
        )
        return self._session.scalars(statement).one_or_none()
