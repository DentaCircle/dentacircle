"""Patient links and persistent-before-dispatch messages."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.integrations.messaging.base import Connection, IncomingText, MessagingProvider
from dentacircle.integrations.messaging.contact_fence import contact_fence
from dentacircle.models.messaging import Message, MessagingContact
from dentacircle.models.patient import Patient
from dentacircle.repositories.messaging_repository import MessagingRepository
from dentacircle.repositories.patient_repository import PatientRepository, send_status_gate
from dentacircle.services.audit_service import record
from dentacircle.services.patient_service import PatientNotFoundError
from dentacircle.services.whatsapp_actor import (
    InvalidWhatsAppActor,
    VerifiedCallback,
    WhatsAppActor,
    resolve_actor,
)


class ContactConflict(Exception):
    """The requested link or request id conflicts with existing state."""


class MessagingUnavailable(Exception):
    """The provider is not currently available."""


class MessagingInvalid(Exception):
    """The supplied input is invalid."""


@dataclass(frozen=True)
class MessageView:
    id: UUID
    direction: str
    origin: str
    body: str
    state: str
    created_at: datetime
    updated_at: datetime
    provider_sent_at: datetime | None
    actor_id: UUID | None
    actor_name: str | None


def _view(repository: MessagingRepository, row: Message) -> MessageView:
    actor = repository.actor(row.created_by_user_id) if row.created_by_user_id else None
    return MessageView(
        id=row.id,
        direction=row.direction,
        origin=row.origin,
        body=row.body,
        state=row.state,
        created_at=row.created_at,
        updated_at=row.updated_at,
        provider_sent_at=row.provider_sent_at,
        actor_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else None,
    )


def _patient(session: Session, clinic_id: UUID, patient_id: UUID) -> Patient:
    patient = PatientRepository(session, clinic_id).get(patient_id)
    if patient is None:
        raise PatientNotFoundError
    return patient


def get_contact(session: Session, clinic_id: UUID, patient_id: UUID) -> MessagingContact | None:
    _patient(session, clinic_id, patient_id)
    return MessagingRepository(session, clinic_id).contact_for_patient(patient_id)


def list_history(
    session: Session, clinic_id: UUID, patient_id: UUID, page: int, page_size: int
) -> tuple[list[MessageView], int]:
    _patient(session, clinic_id, patient_id)
    repo = MessagingRepository(session, clinic_id)
    contact = repo.contact_for_patient(patient_id)
    rows, total = repo.history(contact.id, page, page_size) if contact else ([], 0)
    return [_view(repo, row) for row in rows], total


def list_inbox(
    session: Session, clinic_id: UUID, page: int, page_size: int
) -> tuple[list[tuple[Patient, MessageView, int]], int]:
    repo = MessagingRepository(session, clinic_id)
    rows, total = repo.inbox(page, page_size)
    return [(patient, _view(repo, row), count) for patient, row, count in rows], total


def link_contact(
    session: Session,
    clinic_id: UUID,
    actor_id: UUID,
    patient_id: UUID,
    account: str,
    number: str,
    allowlist: set[str],
) -> MessagingContact:
    patient = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if patient is None:
        raise PatientNotFoundError
    if patient.status != "active":
        raise ContactConflict
    if not re.fullmatch(r"\+[1-9][0-9]{1,14}", number):
        raise MessagingInvalid
    if not account:
        raise MessagingUnavailable
    if number not in allowlist:
        raise ContactConflict
    repository = MessagingRepository(session, clinic_id)
    existing = repository.contact_for_patient(patient_id)
    if existing is not None:
        if existing.number == number and existing.account_key == account:
            return existing
        raise ContactConflict
    if repository.contact_for_number(account, number):
        raise ContactConflict
    row = MessagingContact(
        id=uuid4(),
        patient_id=patient_id,
        account_key=account,
        number=number,
        created_by_user_id=actor_id,
    )
    repository.add_contact(row)
    record(session, clinic_id, actor_id, "messaging_contact", row.id, "create")
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ContactConflict from None
    session.refresh(row)
    return row


def send_message(
    session: Session,
    provider: MessagingProvider,
    clinic_id: UUID,
    actor_id: UUID,
    patient_id: UUID,
    body: str,
    request_id: UUID,
    account: str,
    allowlist: set[str],
) -> tuple[MessageView, bool]:
    body = body.strip()
    if not 1 <= len(body) <= 2000:
        raise MessagingInvalid
    engine = session.get_bind().engine
    # The availability probe is external, so do not hold a patient lock during it.
    with Session(engine) as lookup:
        patient = PatientRepository(lookup, clinic_id).get(patient_id)
        if patient is None:
            raise PatientNotFoundError
        repository = MessagingRepository(lookup, clinic_id)
        contact = repository.contact_for_patient(patient_id)
        prior = repository.by_request(request_id)
        if prior is not None:
            if contact is None or prior.contact_id != contact.id or prior.body != body:
                raise ContactConflict
            return _view(repository, prior), False
        if patient.status != "active" or contact is None:
            raise ContactConflict
        contact_account, number = contact.account_key, contact.number
    connection = provider.connection()
    if connection.status != "connected":
        raise MessagingUnavailable
    if not connection.can_send_text or contact_account != account or number not in allowlist:
        raise ContactConflict
    patient = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if patient is None:
        raise PatientNotFoundError
    repository = MessagingRepository(session, clinic_id)
    contact = repository.contact_for_patient(patient_id)
    prior = repository.by_request(request_id)
    if prior is not None:
        if contact is None or prior.contact_id != contact.id or prior.body != body:
            raise ContactConflict
        return _view(repository, prior), False
    if (
        patient.status != "active"
        or contact is None
        or contact.account_key != account
        or contact.number not in allowlist
    ):
        raise ContactConflict
    contact_id, number = contact.id, contact.number
    row = Message(
        id=uuid4(),
        contact_id=contact.id,
        account_key=contact.account_key,
        direction="outbound",
        origin="staff",
        body=body,
        state="sending",
        created_by_user_id=actor_id,
        request_id=request_id,
    )
    repository.add_message(row)
    record(session, clinic_id, actor_id, "message", row.id, "create")
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        prior = repository.by_request(request_id)
        if prior is None or prior.contact_id != contact_id or prior.body != body:
            raise ContactConflict from None
        return _view(repository, prior), False
    # Staff and automatic replies share the contact fence. The status gate prevents
    # deactivation from committing between this check and the external call.
    with contact_fence(clinic_id, contact_id) as fence:
        if fence is None:
            result = "failed"
        else:
            with send_status_gate(engine, clinic_id, patient_id):
                session.expire_all()
                patient = PatientRepository(session, clinic_id).get(patient_id)
                eligible = patient is not None and patient.status == "active"
                session.rollback()  # release the read transaction before the provider call
                result = provider.send_text(number, body, fence_fd=fence) if eligible else "failed"
    row.state = result
    row.updated_at = datetime.now(UTC)
    record(session, clinic_id, actor_id, "message", row.id, "status_change", ["state"])
    session.commit()
    session.refresh(row)
    return _view(repository, row), True


def receive_message(session: Session, clinic_id: UUID, event: IncomingText) -> None:
    repository = MessagingRepository(session, clinic_id)
    contact = repository.contact_for_number(event.account_key, event.number)
    if contact is None:
        return
    repository.add_incoming(contact, event)
    session.commit()


def connection_status(provider: MessagingProvider) -> Connection:
    return provider.connection()


def receive_event(
    session: Session,
    authority: VerifiedCallback,
    provider: MessagingProvider,
    payload: object,
    on_action: Callable[[Session, WhatsAppActor], None] | None = None,
) -> None:
    """Persist a verified inbound event and its action atomically, once."""
    event = provider.normalize_event(payload)
    if event is None or event.number not in authority.allowlist:
        return
    repository = MessagingRepository(session, authority.clinic_id)
    contact = repository.contact_for_number(event.account_key, event.number)
    if contact is None or event.account_key != authority.account_key:
        return
    message_id = repository.add_incoming(contact, event)
    if message_id is not None and on_action is not None:
        try:
            actor = resolve_actor(session, authority, message_id)
        except InvalidWhatsAppActor:
            actor = None
        if actor is not None:
            on_action(session, actor)
    session.commit()
