"""Append and read audit rows for one clinic. There is no update or delete."""

from uuid import UUID

from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.audit_event import AuditEvent


class AuditRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, event: AuditEvent) -> None:
        event.clinic_id = self._clinic_id
        self._session.add(event)

    def list_for_entity(self, entity_type: str, entity_id: UUID) -> list[AuditEvent]:
        statement = (
            scoped_select(AuditEvent, self._clinic_id)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.occurred_at, AuditEvent.id)
        )
        return list(self._session.scalars(statement))
