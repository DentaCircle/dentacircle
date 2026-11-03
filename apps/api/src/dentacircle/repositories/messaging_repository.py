"""Clinic-scoped messaging reads and writes."""

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from dentacircle.integrations.messaging.base import IncomingText
from dentacircle.models.app_user import AppUser
from dentacircle.models.messaging import Message, MessagingContact
from dentacircle.models.patient import Patient


class MessagingRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self.session = session
        self.clinic_id = clinic_id

    def contact_for_patient(self, patient_id: UUID) -> MessagingContact | None:
        return self.session.scalar(
            select(MessagingContact).where(
                MessagingContact.clinic_id == self.clinic_id,
                MessagingContact.patient_id == patient_id,
            )
        )

    def contact_for_number(self, account: str, number: str) -> MessagingContact | None:
        return self.session.scalar(
            select(MessagingContact).where(
                MessagingContact.clinic_id == self.clinic_id,
                MessagingContact.account_key == account,
                MessagingContact.number == number,
            )
        )

    def by_request(self, request_id: UUID) -> Message | None:
        return self.session.scalar(
            select(Message).where(
                Message.clinic_id == self.clinic_id,
                Message.request_id == request_id,
            )
        )

    def add_contact(self, row: MessagingContact) -> None:
        row.clinic_id = self.clinic_id
        self.session.add(row)

    def add_message(self, row: Message) -> None:
        row.clinic_id = self.clinic_id
        self.session.add(row)

    def add_incoming(self, contact: MessagingContact, event: IncomingText) -> None:
        statement = (
            insert(Message)
            .values(
                id=uuid4(),
                clinic_id=self.clinic_id,
                contact_id=contact.id,
                account_key=event.account_key,
                direction="inbound",
                body=event.body,
                state="received",
                provider_message_id=event.provider_message_id,
                provider_sent_at=event.provider_sent_at,
            )
            .on_conflict_do_nothing(constraint="uq_message_provider_id")
        )
        self.session.execute(statement)

    def history(self, contact_id: UUID, page: int, page_size: int) -> tuple[list[Message], int]:
        query = select(Message).where(
            Message.clinic_id == self.clinic_id, Message.contact_id == contact_id
        )
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self.session.scalars(
            query.order_by(Message.created_at.desc(), Message.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    def inbox(self, page: int, page_size: int) -> tuple[list[tuple[Patient, Message, int]], int]:
        ranked = (
            select(
                Message.id.label("message_id"),
                Message.contact_id,
                func.row_number()
                .over(
                    partition_by=Message.contact_id,
                    order_by=(Message.created_at.desc(), Message.id.desc()),
                )
                .label("rank"),
                func.count().over(partition_by=Message.contact_id).label("message_count"),
            )
            .where(Message.clinic_id == self.clinic_id)
            .subquery()
        )
        query = (
            select(Patient, Message, ranked.c.message_count)
            .join(
                MessagingContact,
                (MessagingContact.patient_id == Patient.id)
                & (MessagingContact.clinic_id == Patient.clinic_id),
            )
            .join(ranked, ranked.c.contact_id == MessagingContact.id)
            .join(
                Message, (Message.id == ranked.c.message_id) & (Message.clinic_id == self.clinic_id)
            )
            .where(Patient.clinic_id == self.clinic_id, ranked.c.rank == 1)
        )
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self.session.execute(
            query.order_by(Message.created_at.desc(), Message.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [(patient, message, count) for patient, message, count in rows], total

    def actor(self, user_id: UUID) -> AppUser | None:
        return self.session.scalar(
            select(AppUser).where(AppUser.clinic_id == self.clinic_id, AppUser.id == user_id)
        )
