"""Patient links and persistent-before-dispatch messages."""

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.integrations.messaging.base import IncomingText, MessagingProvider
from dentacircle.models.messaging import Message, MessagingContact
from dentacircle.repositories.messaging_repository import MessagingRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.audit_service import record
from dentacircle.services.patient_service import PatientNotFoundError


class ContactConflict(Exception):
    """The requested link or request id conflicts with existing state."""


class MessagingUnavailable(Exception):
    """The provider is not currently available."""


class MessagingInvalid(Exception):
    """The supplied input is invalid."""


def link_contact(
    session: Session,
    clinic_id: UUID,
    actor_id: UUID,
    patient_id: UUID,
    account: str,
    number: str,
    allowlist: set[str],
) -> MessagingContact:
    if not re.fullmatch(r"\+[1-9][0-9]{1,14}", number):
        raise MessagingInvalid
    if not account or number not in allowlist:
        raise ContactConflict
    patient = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if patient is None:
        raise PatientNotFoundError
    if patient.status != "active":
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
) -> tuple[Message, bool]:
    body = body.strip()
    if not 1 <= len(body) <= 2000:
        raise MessagingInvalid
    patient = PatientRepository(session, clinic_id).get(patient_id)
    if patient is None:
        raise PatientNotFoundError
    repository = MessagingRepository(session, clinic_id)
    contact = repository.contact_for_patient(patient_id)
    prior = repository.by_request(request_id)
    if prior is not None:
        if contact is None or prior.contact_id != contact.id or prior.body != body:
            raise ContactConflict
        return prior, False
    if patient.status != "active" or contact is None:
        raise ContactConflict
    connection = provider.connection()
    if connection.status != "connected":
        raise MessagingUnavailable
    if (
        not connection.can_send_text
        or contact.account_key != account
        or contact.number not in allowlist
    ):
        raise ContactConflict
    row = Message(
        id=uuid4(),
        contact_id=contact.id,
        account_key=contact.account_key,
        direction="outbound",
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
        if prior is None or prior.contact_id != contact.id or prior.body != body:
            raise ContactConflict from None
        return prior, False
    result = provider.send_text(contact.number, body)
    row.state = result
    row.updated_at = datetime.now(UTC)
    record(session, clinic_id, actor_id, "message", row.id, "status_change", ["state"])
    session.commit()
    session.refresh(row)
    return row, True


def receive_message(session: Session, clinic_id: UUID, event: IncomingText) -> None:
    repository = MessagingRepository(session, clinic_id)
    contact = repository.contact_for_number(event.account_key, event.number)
    if contact is None:
        return
    repository.add_incoming(contact, event)
    session.commit()
