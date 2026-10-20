"""Reads and writes for one clinic's recalls. Every method takes that clinic."""

from uuid import UUID

from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.domain.recall import OPEN_RECALL_STATUSES
from dentacircle.models.recall import Recall


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
