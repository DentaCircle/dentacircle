"""Staff control over a linked contact's booking automation."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from dentacircle.models.messaging import MessagingContact
from dentacircle.models.whatsapp_booking_session import WhatsAppBookingSession
from dentacircle.repositories.messaging_repository import MessagingRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.audit_service import record
from dentacircle.services.patient_service import PatientNotFoundError
from dentacircle.services.whatsapp_actor import WhatsAppActor


class AutomationConflict(Exception):
    """The linked contact cannot change automation state."""


def transition(
    session: Session,
    clinic_id: UUID,
    contact: MessagingContact,
    actor: UUID | WhatsAppActor,
    state: Literal["active", "staff_handling", "needs_staff", "stopped"],
) -> None:
    """Invalidate choices on each control action while the caller holds the patient lock."""
    contact.automation_state = state
    contact.automation_version += 1
    contact.automation_changed_at = datetime.now(UTC)
    session.execute(
        update(WhatsAppBookingSession)
        .where(
            WhatsAppBookingSession.clinic_id == clinic_id,
            WhatsAppBookingSession.contact_id == contact.id,
            WhatsAppBookingSession.state.in_(
                ("resume_challenge", "visits", "source", "type", "slots", "confirmation")
            ),
        )
        .values(state="stopped", updated_at=contact.automation_changed_at)
    )
    record(
        session, clinic_id, actor, "messaging_contact", contact.id, "update", ["automation_state"]
    )


def set_staff_automation(
    session: Session,
    clinic_id: UUID,
    actor: UUID,
    patient_id: UUID,
    state: Literal["active", "staff_handling"],
    account: str,
    allowlist: set[str],
) -> MessagingContact:
    patient = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if patient is None:
        raise PatientNotFoundError
    contact = MessagingRepository(session, clinic_id).contact_for_patient(patient_id, lock=True)
    if patient.status != "active" or contact is None:
        raise AutomationConflict
    if state == "active" and (contact.account_key != account or contact.number not in allowlist):
        raise AutomationConflict
    transition(session, clinic_id, contact, actor, state)
    session.commit()
    session.refresh(contact)
    return contact
