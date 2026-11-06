"""Reads and writes for one clinic's patients. Every method takes that clinic."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, false, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from dentacircle.core.tenancy import scoped_select
from dentacircle.domain.patient import SearchFilter
from dentacircle.models.patient import Patient


def _status_gate_key(clinic_id: UUID, patient_id: UUID) -> int:
    digest = hashlib.blake2b(clinic_id.bytes + patient_id.bytes, digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


@contextmanager
def send_status_gate(engine: Engine, clinic_id: UUID, patient_id: UUID) -> Iterator[None]:
    """Hold a session advisory gate, without an open transaction, during a send."""
    key = _status_gate_key(clinic_id, patient_id)
    with engine.connect() as connection:
        connection.execute(select(func.pg_advisory_lock(key)))
        connection.commit()
        try:
            yield
        finally:
            connection.execute(select(func.pg_advisory_unlock(key)))
            connection.commit()


class PatientRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def lock_status_gate(self, patient_id: UUID) -> None:
        """Serialize a status change with a provider send through commit."""
        self._session.execute(
            select(func.pg_advisory_xact_lock(_status_gate_key(self._clinic_id, patient_id)))
        )

    def allocate_number(self) -> int:
        """Take the next number. The upsert locks this clinic's counter row until commit."""
        allocated: int = self._session.execute(
            text(
                "INSERT INTO patient_number_counter (clinic_id, last_number) "
                "VALUES (:clinic_id, 1) "
                "ON CONFLICT (clinic_id) DO UPDATE "
                "SET last_number = patient_number_counter.last_number + 1 "
                "RETURNING last_number"
            ),
            {"clinic_id": self._clinic_id},
        ).scalar_one()
        return allocated

    def add(self, patient: Patient) -> None:
        patient.clinic_id = self._clinic_id
        self._session.add(patient)

    def get(self, patient_id: UUID, *, lock: bool = False) -> Patient | None:
        statement = scoped_select(Patient, self._clinic_id).where(Patient.id == patient_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(Patient | None, self._session.scalar(statement))

    def search(
        self,
        search_filter: SearchFilter,
        page: int,
        page_size: int,
        *,
        status: str | None = None,
    ) -> tuple[list[Patient], int]:
        statement = scoped_select(Patient, self._clinic_id)
        clause = _clause(search_filter)
        if clause is not None:
            statement = statement.where(clause)
        if status is not None:
            statement = statement.where(Patient.status == status)
        total = self._session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self._session.scalars(
            statement.order_by(func.lower(Patient.full_name), Patient.patient_number)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)


def _clause(search_filter: SearchFilter) -> ColumnElement[bool] | None:
    if search_filter.mode == "all":
        return None
    if search_filter.mode == "none":
        return false()
    if search_filter.mode == "number":
        return Patient.patient_number == search_filter.patient_number
    if search_filter.mode == "phone":
        return _contains(Patient.phone_digits, search_filter.phone_digits)
    return and_(
        *(_contains(func.lower(Patient.full_name), word) for word in search_filter.name_words)
    )


def _contains(column: Any, value: str) -> ColumnElement[bool]:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return cast(ColumnElement[bool], column.like(f"%{escaped}%", escape="\\"))
