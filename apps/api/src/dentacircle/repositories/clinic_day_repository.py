"""Reads and writes for one clinic's timezone, duration and open intervals."""

from datetime import time
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.clinic import Clinic
from dentacircle.models.working_hours import ClinicWorkingHours


class ClinicDayRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def get_clinic(self) -> Clinic | None:
        # `clinic` is the tenant root, so the row id is the scope. It has no clinic_id column.
        clinic = self._session.get(Clinic, self._clinic_id)
        if clinic is None:
            return None
        return clinic

    def list_hours(self) -> list[ClinicWorkingHours]:
        statement = scoped_select(ClinicWorkingHours, self._clinic_id).order_by(
            ClinicWorkingHours.weekday, ClinicWorkingHours.opens_at
        )
        return list(self._session.scalars(statement))

    def replace_hours(self, intervals: list[tuple[int, time, time]]) -> None:
        self._session.execute(
            delete(ClinicWorkingHours).where(ClinicWorkingHours.clinic_id == self._clinic_id)
        )
        for weekday, opens_at, closes_at in intervals:
            self._session.add(
                ClinicWorkingHours(
                    clinic_id=self._clinic_id,
                    weekday=weekday,
                    opens_at=opens_at,
                    closes_at=closes_at,
                )
            )
