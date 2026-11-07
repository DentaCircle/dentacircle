"""Claim and send queued replies under a per-contact local process fence."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dentacircle.integrations.messaging.base import MessagingProvider, SendStatus
from dentacircle.integrations.messaging.bounded import bounded_send
from dentacircle.integrations.messaging.contact_fence import contact_fence
from dentacircle.models.messaging import Message, MessagingContact
from dentacircle.models.patient import Patient
from dentacircle.repositories.automatic_dispatch_repository import AutomaticDispatchRepository
from dentacircle.repositories.patient_repository import PatientRepository, send_status_gate
from dentacircle.services.audit_service import record
from dentacircle.services.whatsapp_actor import WhatsAppActor
from dentacircle.services.whatsapp_booking_service import BookingResultUnavailable

DispatchResult = Literal["busy", "idle", "sent", "superseded"]
Guard = Callable[[Session, Message], str | None]
_SEND_SECONDS = 10.0


def _status(
    session: Session, clinic_id: UUID, row: Message, actor: WhatsAppActor, state: str
) -> None:
    row.state = state
    row.dispatch_owner = None
    row.dispatch_deadline_at = None
    row.updated_at = datetime.now(UTC)
    record(session, clinic_id, actor, "message", row.id, "status_change", ["state"])


def _eligible(
    row: Message,
    identity: tuple[MessagingContact, Patient, Message],
    account: str,
    allowlist: set[str],
) -> bool:
    contact, patient, cause = identity
    return (
        patient.status == "active"
        and contact.number in allowlist
        and contact.account_key == account
        and row.account_key == account
        and cause.account_key == account
        and cause.contact_id == contact.id
        and cause.origin == "provider"
        and cause.direction == "inbound"
        and cause.state == "received"
    )


def dispatch_one(
    engine: Engine,
    provider: MessagingProvider,
    clinic_id: UUID,
    contact_id: UUID,
    account: str,
    allowlist: set[str],
    guard: Guard | None = None,
) -> DispatchResult:
    """A fence owner recovers abandoned claims, then attempts at most one queued reply."""
    with contact_fence(clinic_id, contact_id) as fd:
        if fd is None:
            return "busy"
        with Session(engine) as session:
            patient_id = AutomaticDispatchRepository(session, clinic_id).patient_id(contact_id)
        if patient_id is None:
            return "idle"
        # The gate serializes deactivation before eligibility is checked. No row lock
        # or transaction remains open during the provider call.
        with send_status_gate(engine, clinic_id, patient_id):
            return _dispatch_fenced(
                engine, provider, clinic_id, contact_id, account, allowlist, guard, fd
            )


def _dispatch_fenced(
    engine: Engine,
    provider: MessagingProvider,
    clinic_id: UUID,
    contact_id: UUID,
    account: str,
    allowlist: set[str],
    guard: Guard | None,
    fd: int,
) -> DispatchResult:
    with Session(engine, expire_on_commit=False) as session:
        repo = AutomaticDispatchRepository(session, clinic_id)
        patient_id = repo.patient_id(contact_id)
        if patient_id is None:
            return "idle"
        # Serialize result rendering and the durable claim with staff visit changes.
        if PatientRepository(session, clinic_id).get(patient_id, lock=True) is None:
            return "idle"
        while (row := repo.next_outstanding(contact_id)) is not None:
            identity = repo.identity(row)
            if identity is None:
                raise RuntimeError("automatic reply identity is missing")
            contact, patient, cause = identity
            actor = WhatsAppActor(clinic_id, patient.id, cause.id, cause.account_key)
            if row.state == "sending":
                _status(session, clinic_id, row, actor, "unknown")
                session.flush()
                continue
            eligible = _eligible(row, identity, account, allowlist)
            try:
                rendered = (guard(session, row) if guard else row.body) if eligible else None
            except BookingResultUnavailable:
                session.rollback()
                return "idle"
            if rendered is None or not 1 <= len(rendered) <= 2000:
                _status(session, clinic_id, row, actor, "superseded")
                session.commit()
                return "superseded"
            owner = uuid4()
            row.body = rendered
            row.state = "sending"
            row.dispatch_owner = owner
            row.dispatch_deadline_at = datetime.now(UTC) + timedelta(seconds=_SEND_SECONDS)
            row.updated_at = datetime.now(UTC)
            record(session, clinic_id, actor, "message", row.id, "status_change", ["state"])
            message_id, number, body = row.id, contact.number, row.body
            session.commit()
            break
        else:
            session.commit()
            return "idle"
    outcome: SendStatus = bounded_send(
        provider, number, body, timeout_seconds=_SEND_SECONDS, fence_fd=fd
    )
    with Session(engine) as session:
        claimed = AutomaticDispatchRepository(session, clinic_id).claimed(message_id, owner)
        if claimed is not None:
            _status(session, clinic_id, claimed, actor, outcome)
            session.commit()
    return "sent"
