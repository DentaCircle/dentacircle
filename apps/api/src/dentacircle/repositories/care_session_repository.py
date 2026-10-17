"""Reads and writes for one clinic's care sessions. Every method takes that clinic."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.app_user import AppUser
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_plan import CarePlan
from dentacircle.models.care_session import CareSession
from dentacircle.models.care_session_item import CareSessionItem


class CareSessionRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, row: CareSession) -> None:
        row.clinic_id = self._clinic_id
        self._session.add(row)

    def add_item(self, row: CareSessionItem) -> None:
        row.clinic_id = self._clinic_id
        self._session.add(row)

    def get_for_appointment(self, appointment_id: UUID) -> CareSession | None:
        statement = scoped_select(CareSession, self._clinic_id).where(
            CareSession.appointment_id == appointment_id
        )
        return self._session.scalars(statement).one_or_none()

    def user_name(self, user_id: UUID) -> str:
        statement = scoped_select(AppUser, self._clinic_id).where(AppUser.id == user_id)
        user = self._session.scalars(statement).one()
        return str(user.full_name)

    def list_lines(self, session_id: UUID) -> list[tuple[CareSessionItem, str, str]]:
        """Session lines with the item's current name and its plan's current title."""
        statement = (
            select(CareSessionItem, CareItem.name, CarePlan.title)
            .join(
                CareItem,
                (CareItem.id == CareSessionItem.care_item_id)
                & (CareItem.clinic_id == self._clinic_id),
            )
            .join(
                CarePlan,
                (CarePlan.id == CareItem.care_plan_id) & (CarePlan.clinic_id == self._clinic_id),
            )
            .where(
                CareSessionItem.clinic_id == self._clinic_id,
                CareSessionItem.care_session_id == session_id,
            )
            .order_by(CareSessionItem.created_at, CareSessionItem.id)
        )
        rows = self._session.execute(statement).all()
        return [(line, name, title) for line, name, title in rows]
