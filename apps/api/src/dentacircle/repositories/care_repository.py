"""Reads and writes for one clinic's care plans. Every method takes that clinic."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_plan import CarePlan


class CareRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add_plan(self, plan: CarePlan) -> None:
        plan.clinic_id = self._clinic_id
        self._session.add(plan)

    def add_item(self, item: CareItem) -> None:
        item.clinic_id = self._clinic_id
        self._session.add(item)

    def get_plan(self, plan_id: UUID) -> CarePlan | None:
        statement = scoped_select(CarePlan, self._clinic_id).where(CarePlan.id == plan_id)
        return self._session.scalars(statement).one_or_none()

    def get_item(self, item_id: UUID) -> CareItem | None:
        statement = scoped_select(CareItem, self._clinic_id).where(CareItem.id == item_id)
        return self._session.scalars(statement).one_or_none()

    def get_item_for_update(self, item_id: UUID) -> CareItem | None:
        """Lock the row so two status moves of the same item cannot both succeed."""
        statement = (
            scoped_select(CareItem, self._clinic_id).where(CareItem.id == item_id).with_for_update()
        )
        return self._session.scalars(
            statement,
            execution_options={"populate_existing": True},
        ).one_or_none()

    def list_plans(self, patient_id: UUID) -> list[CarePlan]:
        statement = (
            scoped_select(CarePlan, self._clinic_id)
            .where(CarePlan.patient_id == patient_id)
            .order_by(CarePlan.created_at.desc(), CarePlan.id.desc())
        )
        return list(self._session.scalars(statement))

    def list_items(self, plan_ids: list[UUID]) -> list[CareItem]:
        if not plan_ids:
            return []
        statement = (
            scoped_select(CareItem, self._clinic_id)
            .where(CareItem.care_plan_id.in_(plan_ids))
            .order_by(CareItem.created_at.asc(), CareItem.id.asc())
        )
        return list(self._session.scalars(statement))

    def list_item_statuses(self, patient_id: UUID) -> list[str]:
        """Every item status on this patient's plans, including items never put in a session."""
        statement = (
            select(CareItem.status)
            .join(
                CarePlan,
                (CarePlan.id == CareItem.care_plan_id) & (CarePlan.clinic_id == self._clinic_id),
            )
            .where(CareItem.clinic_id == self._clinic_id, CarePlan.patient_id == patient_id)
        )
        return list(self._session.scalars(statement))
