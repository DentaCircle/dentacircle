"""Persist an automatic reply in the inbound action's transaction."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from dentacircle.models.messaging import Message
from dentacircle.services.audit_service import record
from dentacircle.services.whatsapp_actor import WhatsAppActor, require_patient


class InvalidReply(Exception):
    """Automatic text must fit the messaging contract."""


def queue_reply(session: Session, actor: WhatsAppActor, body: str) -> Message:
    body = body.strip()
    if not 1 <= len(body) <= 2000:
        raise InvalidReply
    require_patient(session, actor, actor.clinic_id, actor.patient_id)
    incoming = session.scalar(
        select(Message).where(Message.id == actor.message_id, Message.clinic_id == actor.clinic_id)
    )
    if incoming is None:
        raise InvalidReply
    reply_id = uuid4()
    inserted = session.scalar(
        insert(Message)
        .values(
            id=reply_id,
            clinic_id=actor.clinic_id,
            contact_id=incoming.contact_id,
            account_key=incoming.account_key,
            direction="outbound",
            origin="automation",
            caused_by_message_id=incoming.id,
            body=body,
            state="queued",
        )
        .on_conflict_do_nothing(constraint="uq_message_cause")
        .returning(Message.id)
    )
    if inserted is not None:
        record(session, actor.clinic_id, actor, "message", inserted, "create")
    result = session.scalar(
        select(Message).where(
            Message.clinic_id == actor.clinic_id, Message.caused_by_message_id == actor.message_id
        )
    )
    if result is None:
        raise RuntimeError("automatic reply could not be loaded")
    return result
