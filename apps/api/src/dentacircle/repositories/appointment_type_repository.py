"""Reads and writes for one clinic's appointment types."""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.appointment_type import AppointmentType


class AppointmentTypeRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def list_types(self, include_inactive: bool) -> list[AppointmentType]:
        statement = scoped_select(AppointmentType, self._clinic_id)
        if not include_inactive:
            statement = statement.where(AppointmentType.is_active.is_(True))
        statement = statement.order_by(func.lower(AppointmentType.name), AppointmentType.name)
        return list(self._session.scalars(statement))

    def get(self, type_id: UUID) -> AppointmentType | None:
        statement = scoped_select(AppointmentType, self._clinic_id).where(
            AppointmentType.id == type_id
        )
        return self._session.scalars(statement).one_or_none()

    def find_by_name(self, name: str) -> AppointmentType | None:
        statement = scoped_select(AppointmentType, self._clinic_id).where(
            func.lower(AppointmentType.name) == name.strip().lower()
        )
        return self._session.scalars(statement).one_or_none()

    def add(self, appointment_type: AppointmentType) -> None:
        appointment_type.clinic_id = self._clinic_id
        self._session.add(appointment_type)
