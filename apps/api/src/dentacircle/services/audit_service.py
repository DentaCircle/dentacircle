"""The one place that builds an audit event. Callers do not assemble the row themselves."""

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from dentacircle.domain.audit import AUDIT_ACTIONS
from dentacircle.models.audit_event import AuditEvent
from dentacircle.repositories.audit_repository import AuditRepository


class UnknownAuditActionError(Exception):
    """An action outside the four the audit table allows."""


def record(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    entity_type: str,
    entity_id: UUID,
    action: str,
) -> None:
    if action not in AUDIT_ACTIONS:
        raise UnknownAuditActionError
    AuditRepository(session, clinic_id).add(
        AuditEvent(
            id=uuid4(),
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
        )
    )
