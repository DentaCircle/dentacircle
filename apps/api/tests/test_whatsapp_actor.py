"""Message attribution follows the verified contact, never a submitted patient id."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.config import Settings
from dentacircle.core.database import get_engine
from dentacircle.integrations.messaging.base import IncomingText
from dentacircle.models.messaging import Message
from dentacircle.services.messaging_service import link_contact, receive_message
from dentacircle.services.whatsapp_actor import (
    InvalidWhatsAppActor,
    VerifiedCallback,
    authenticate_callback,
    require_patient,
    resolve_actor,
)
from tests.timeline_support import world

pytest_plugins = ["tests.timeline_support"]


def authority(
    clinic_id: UUID, account: str = "demo", numbers: str = "+15551234567"
) -> VerifiedCallback:
    settings = Settings(
        database_url="postgresql://unused",
        messaging_clinic_id=str(clinic_id),
        messaging_account=account,
        messaging_callback_secret="secret",
        messaging_allowlist=numbers,
        _env_file=None,
    )
    return authenticate_callback("secret", settings)


def test_actor_requires_the_linked_allowlisted_inbound_message(database: str) -> None:
    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )
        receive_message(
            session, clinic.clinic_id, IncomingText("demo", number, "id-1", "BOOK", None)
        )
        message = session.scalar(select(Message).where(Message.clinic_id == clinic.clinic_id))
        assert message is not None
        with pytest.raises(InvalidWhatsAppActor):
            resolve_actor(
                session, VerifiedCallback(clinic.clinic_id, "demo", frozenset({number})), message.id
            )
        actor = resolve_actor(session, authority(clinic.clinic_id), message.id)
        assert actor.patient_id == clinic.patient_id
        require_patient(session, actor, clinic.clinic_id, clinic.patient_id)
        with pytest.raises(InvalidWhatsAppActor):
            require_patient(session, actor, clinic.clinic_id, uuid4())
        with pytest.raises(InvalidWhatsAppActor):
            resolve_actor(session, authority(clinic.clinic_id, "other"), message.id)
        with pytest.raises(InvalidWhatsAppActor):
            resolve_actor(session, authority(clinic.clinic_id, numbers=""), message.id)
        with pytest.raises(InvalidWhatsAppActor):
            resolve_actor(session, authority(uuid4()), message.id)


def test_booking_records_the_message_actor_and_rejects_forgery(database: str) -> None:
    from sqlalchemy import select

    from dentacircle.models.audit_event import AuditEvent
    from dentacircle.models.timeline_event import TimelineEvent
    from dentacircle.services.appointment_service import book_appointment
    from dentacircle.services.timeline_service import list_timeline
    from dentacircle.services.whatsapp_actor import WhatsAppActor
    from tests.test_appointment_service import _NOW, _at, _world

    clinic_id, staff_id, clinician_id, patient_id, type_id = _world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(session, clinic_id, staff_id, patient_id, "demo", number, {number})
        receive_message(session, clinic_id, IncomingText("demo", number, "id-1", "BOOK", None))
        message = session.scalar(select(Message).where(Message.clinic_id == clinic_id))
        assert message is not None
        forged = WhatsAppActor(clinic_id, patient_id, message.id, "demo")
        with pytest.raises(InvalidWhatsAppActor):
            book_appointment(
                session, clinic_id, forged, patient_id, clinician_id, type_id, _at(1, 9, 0), _NOW
            )
        session.rollback()
        actor = resolve_actor(session, authority(clinic_id), message.id)
        appointment = book_appointment(
            session, clinic_id, actor, patient_id, clinician_id, type_id, _at(1, 9, 0), _NOW
        )
        session.commit()
        audit = session.scalar(select(AuditEvent).where(AuditEvent.entity_id == appointment.id))
        event = session.scalar(
            select(TimelineEvent).where(TimelineEvent.appointment_id == appointment.id)
        )
        assert audit is not None and event is not None
        assert (audit.actor_kind, audit.actor_user_id, audit.actor_message_id) == (
            "whatsapp",
            None,
            message.id,
        )
        assert (event.actor_kind, event.actor_user_id, event.actor_message_id) == (
            "whatsapp",
            None,
            message.id,
        )
        items = list_timeline(session, clinic_id, patient_id, 1, 20).items
        booked = next(item for item in items if item.kind == "visit_booked")
        assert (booked.actor.kind, booked.actor.id, booked.actor.name) == (
            "whatsapp",
            None,
            "Patient via WhatsApp",
        )


def test_reply_is_queued_once_with_the_inbound_message_transaction(database: str) -> None:
    from dentacircle.services.automatic_reply_service import queue_reply

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )
        receive_message(
            session, clinic.clinic_id, IncomingText("demo", number, "id-1", "BOOK", None)
        )
        incoming = session.scalar(select(Message).where(Message.clinic_id == clinic.clinic_id))
        assert incoming is not None
        actor = resolve_actor(session, authority(clinic.clinic_id), incoming.id)
        first = queue_reply(session, actor, "Choose an option")
        session.flush()
        second = queue_reply(session, actor, "Choose an option")
        assert first.id == second.id
        assert (first.origin, first.state, first.caused_by_message_id) == (
            "automation",
            "queued",
            incoming.id,
        )
        session.rollback()
        rows = session.scalars(select(Message).where(Message.clinic_id == clinic.clinic_id)).all()
        assert len(rows) == 1


def test_verified_callback_action_and_reply_commit_once(database: str) -> None:
    from dentacircle.integrations.messaging.base import Connection, SendStatus
    from dentacircle.services.automatic_reply_service import queue_reply
    from dentacircle.services.messaging_service import receive_event
    from dentacircle.services.whatsapp_actor import WhatsAppActor

    clinic = world()
    number = "+15551234567"

    class IncomingProvider:
        def connection(self) -> Connection:
            return Connection("connected", True)

        def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> SendStatus:
            return "accepted"

        def normalize_event(self, payload: object) -> IncomingText | None:
            return IncomingText("demo", number, "event-1", "BOOK", None)

    calls: list[UUID] = []

    def action(session: Session, actor: WhatsAppActor) -> None:
        calls.append(actor.message_id)
        queue_reply(session, actor, "Welcome")

    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )
        receive_event(session, authority(clinic.clinic_id), IncomingProvider(), {}, action)
        receive_event(session, authority(clinic.clinic_id), IncomingProvider(), {}, action)
        rows = session.scalars(select(Message).where(Message.clinic_id == clinic.clinic_id)).all()
        assert len(calls) == 1
        assert sorted(row.origin for row in rows) == ["automation", "provider"]
        assert next(row for row in rows if row.origin == "automation").state == "queued"


def test_callback_action_failure_rolls_back_inbound_and_reply(database: str) -> None:
    from dentacircle.integrations.messaging.base import Connection, SendStatus
    from dentacircle.services.automatic_reply_service import queue_reply
    from dentacircle.services.messaging_service import receive_event
    from dentacircle.services.whatsapp_actor import WhatsAppActor

    clinic = world()
    number = "+15551234567"

    class IncomingProvider:
        def connection(self) -> Connection:
            return Connection("connected", True)

        def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> SendStatus:
            return "accepted"

        def normalize_event(self, payload: object) -> IncomingText | None:
            return IncomingText("demo", number, "event-2", "BOOK", None)

    def action(session: Session, actor: WhatsAppActor) -> None:
        queue_reply(session, actor, "Welcome")
        raise RuntimeError("synthetic failure")

    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )
        with pytest.raises(RuntimeError):
            receive_event(session, authority(clinic.clinic_id), IncomingProvider(), {}, action)
        session.rollback()
        assert (
            session.scalars(select(Message).where(Message.clinic_id == clinic.clinic_id)).all()
            == []
        )


def test_whatsapp_actor_books_only_its_own_follow_up(database: str) -> None:
    from dentacircle.models.follow_up import FollowUp
    from dentacircle.services.follow_up_service import book_follow_up, create_manual_follow_up
    from dentacircle.services.patient_service import register_patient
    from tests.timeline_support import AT_START, NOW

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )
        receive_message(
            session, clinic.clinic_id, IncomingText("demo", number, "id-followup", "BOOK", None)
        )
        incoming = session.scalar(select(Message).where(Message.clinic_id == clinic.clinic_id))
        assert incoming is not None
        actor = resolve_actor(session, authority(clinic.clinic_id), incoming.id)
        other = register_patient(
            session, clinic.clinic_id, clinic.actor_id, "Sample Other", "9000000002", None
        )
        own = create_manual_follow_up(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, NOW.date(), NOW
        )
        foreign = create_manual_follow_up(
            session, clinic.clinic_id, clinic.actor_id, other.id, NOW.date(), NOW
        )
        session.commit()
        with pytest.raises(InvalidWhatsAppActor):
            book_follow_up(
                session,
                clinic.clinic_id,
                actor,
                foreign.id,
                clinic.clinician_id,
                clinic.consultation_id,
                AT_START,
                NOW,
            )
        session.rollback()
        visit = book_follow_up(
            session,
            clinic.clinic_id,
            actor,
            own.id,
            clinic.clinician_id,
            clinic.consultation_id,
            AT_START,
            NOW,
        )
        session.commit()
        own_row = session.get(FollowUp, own.id)
        foreign_row = session.get(FollowUp, foreign.id)
        assert own_row is not None and foreign_row is not None
        assert (own_row.status, own_row.booked_appointment_id) == ("booked", visit.id)
        assert foreign_row.status == "scheduled"


def test_whatsapp_actor_books_an_explicit_recall(database: str) -> None:
    from dentacircle.models.recall import Recall
    from dentacircle.services.recall_service import book_recall
    from tests.timeline_support import AT_START, NOW, book, later, move

    clinic = world()
    visit_id = book(clinic, AT_START, clinic.scaling_id)
    move(clinic, visit_id, "arrived")
    move(clinic, visit_id, "in_progress")
    move(clinic, visit_id, "completed")
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )
        receive_message(
            session, clinic.clinic_id, IncomingText("demo", number, "id-recall", "BOOK", None)
        )
        incoming = session.scalar(select(Message).where(Message.clinic_id == clinic.clinic_id))
        recall = session.scalar(
            select(Recall).where(
                Recall.clinic_id == clinic.clinic_id, Recall.patient_id == clinic.patient_id
            )
        )
        assert incoming is not None and recall is not None
        actor = resolve_actor(session, authority(clinic.clinic_id), incoming.id)
        next_visit = book_recall(
            session,
            clinic.clinic_id,
            actor,
            recall.id,
            clinic.clinician_id,
            clinic.consultation_id,
            later(60),
            NOW,
        )
        session.commit()
        assert (recall.status, recall.booked_appointment_id) == ("booked", next_visit.id)
