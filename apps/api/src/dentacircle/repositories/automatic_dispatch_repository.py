"""Clinic-scoped persistence for automatic dispatch."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.models.messaging import Message, MessagingContact
from dentacircle.models.patient import Patient


class AutomaticDispatchRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self.session = session
        self.clinic_id = clinic_id

    def patient_id(self, contact_id: UUID) -> UUID | None:
        return self.session.scalar(
            select(MessagingContact.patient_id).where(
                MessagingContact.clinic_id == self.clinic_id, MessagingContact.id == contact_id
            )
        )

    def pending_contacts(self) -> list[UUID]:
        return list(
            self.session.scalars(
                select(Message.contact_id)
                .where(
                    Message.clinic_id == self.clinic_id,
                    Message.origin == "automation",
                    Message.state.in_(("queued", "sending")),
                )
                .group_by(Message.contact_id)
                .order_by(Message.contact_id)
            )
        )

    def next_outstanding(self, contact_id: UUID) -> Message | None:
        return self.session.scalar(
            select(Message)
            .where(
                Message.clinic_id == self.clinic_id,
                Message.contact_id == contact_id,
                Message.origin == "automation",
                Message.state.in_(("queued", "sending")),
            )
            .order_by(Message.dispatch_order)
            .limit(1)
            .with_for_update()
        )

    def identity(self, message: Message) -> tuple[MessagingContact, Patient, Message] | None:
        result = self.session.execute(
            select(MessagingContact, Patient, Message)
            .join(
                Patient,
                (Patient.id == MessagingContact.patient_id)
                & (Patient.clinic_id == MessagingContact.clinic_id),
            )
            .join(
                Message,
                (Message.id == message.caused_by_message_id)
                & (Message.clinic_id == MessagingContact.clinic_id),
            )
            .where(
                MessagingContact.clinic_id == self.clinic_id,
                MessagingContact.id == message.contact_id,
            )
        ).one_or_none()
        if result is None:
            return None
        contact, patient, cause = result
        return contact, patient, cause

    def claimed(self, message_id: UUID, owner: UUID) -> Message | None:
        return self.session.scalar(
            select(Message)
            .where(
                Message.id == message_id,
                Message.clinic_id == self.clinic_id,
                Message.origin == "automation",
                Message.state == "sending",
                Message.dispatch_owner == owner,
            )
            .with_for_update()
        )
