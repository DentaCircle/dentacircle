"""A delayed BOOK cannot unpause a contact without a fresh challenge."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.integrations.messaging.base import IncomingText
from dentacircle.models.messaging import Message
from dentacircle.models.whatsapp_booking_session import WhatsAppBookingSession
from dentacircle.repositories.messaging_repository import MessagingRepository
from dentacircle.services.messaging_service import link_contact, receive_message
from dentacircle.services.whatsapp_actor import resolve_actor
from dentacircle.services.whatsapp_booking_service import process_action
from tests.test_whatsapp_actor import authority
from tests.timeline_support import world

pytest_plugins = ["tests.timeline_support"]


def test_pause_requires_current_fresh_challenge(database: str) -> None:
    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )

        def send(body: str) -> Message | None:
            event_id = str(uuid4())
            receive_message(
                session, clinic.clinic_id, IncomingText("demo", number, event_id, body, None)
            )
            incoming = session.scalar(
                select(Message).where(Message.provider_message_id == event_id)
            )
            assert incoming is not None
            process_action(
                session, resolve_actor(session, authority(clinic.clinic_id), incoming.id)
            )
            session.commit()
            return session.scalar(
                select(Message).where(Message.caused_by_message_id == incoming.id)
            )

        send("STOP")
        contact = MessagingRepository(session, clinic.clinic_id).contact_for_patient(
            clinic.patient_id
        )
        assert contact is not None and contact.automation_state == "stopped"
        send("BOOK")
        challenge = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.contact_id == contact.id,
                WhatsAppBookingSession.state == "resume_challenge",
            )
        )
        assert challenge is not None and contact.automation_state == "stopped"
        code = challenge.menu_token
        expires = challenge.expires_at
        send("BOOK")
        session.refresh(challenge)
        assert challenge.menu_token == code and challenge.expires_at == expires
        send("BOOK WRONG")
        session.refresh(contact)
        assert contact.automation_state == "stopped"
        send(f"BOOK {code}")
        session.refresh(contact)
        assert contact.automation_state == "active"
        send("STOP")
        send(f"BOOK {code}")
        session.refresh(contact)
        assert contact.automation_state == "stopped"
        send("BOOK")
        challenge = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.contact_id == contact.id,
                WhatsAppBookingSession.state == "resume_challenge",
            )
        )
        assert challenge is not None
        code = challenge.menu_token
        challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        send(f"BOOK {code}")
        session.refresh(contact)
        assert contact.automation_state == "stopped"


def test_visits_are_read_in_bounded_pages_beyond_staff_limit(database: str) -> None:
    from datetime import timedelta

    from dentacircle.models.appointment import Appointment
    from dentacircle.repositories.appointment_repository import AppointmentRepository
    from tests.timeline_support import AT_START

    clinic = world()
    with Session(get_engine(), expire_on_commit=False) as session:
        for index in range(23):
            start = AT_START + timedelta(days=index)
            session.add(
                Appointment(
                    id=uuid4(),
                    clinic_id=clinic.clinic_id,
                    patient_id=clinic.patient_id,
                    clinician_user_id=clinic.clinician_id,
                    appointment_type_id=clinic.consultation_id,
                    starts_at=start,
                    ends_at=start + timedelta(minutes=30),
                    status="scheduled",
                )
            )
        session.commit()
        repo = AppointmentRepository(session, clinic.clinic_id)
        cursor = None
        seen: list[UUID] = []
        while True:
            rows = repo.booking_upcoming_page(
                clinic.patient_id, AT_START - timedelta(days=1), cursor
            )
            assert len(rows) <= 5
            if not rows:
                break
            seen.extend(row[0].id for row in rows)
            cursor = (rows[-1][0].starts_at, rows[-1][0].id)
        assert len(seen) == len(set(seen)) == 23
        assert not repo.booking_upcoming_page(uuid4(), AT_START - timedelta(days=1), None)


def test_existing_visits_must_be_paged_before_additional_booking(database: str) -> None:
    from sqlalchemy import func

    from dentacircle.models.appointment import Appointment
    from dentacircle.repositories.clinic_day_repository import ClinicDayRepository

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        for index in range(23):
            start = datetime.now(UTC) + timedelta(days=index + 1)
            session.add(
                Appointment(
                    id=uuid4(),
                    clinic_id=clinic.clinic_id,
                    patient_id=clinic.patient_id,
                    clinician_user_id=clinic.clinician_id,
                    appointment_type_id=clinic.consultation_id,
                    starts_at=start,
                    ends_at=start + timedelta(minutes=30),
                    status="scheduled",
                )
            )
        session.commit()
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )

        def send(body: str) -> Message:
            event_id = str(uuid4())
            receive_message(
                session, clinic.clinic_id, IncomingText("demo", number, event_id, body, None)
            )
            incoming = session.scalar(
                select(Message).where(Message.provider_message_id == event_id)
            )
            assert incoming is not None
            process_action(
                session, resolve_actor(session, authority(clinic.clinic_id), incoming.id)
            )
            session.commit()
            reply = session.scalar(
                select(Message).where(Message.caused_by_message_id == incoming.id)
            )
            assert reply is not None
            return reply

        reply = send("BOOK")
        booking = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.state == "visits",
                WhatsAppBookingSession.clinic_id == clinic.clinic_id,
            )
        )
        assert booking is not None
        assert len(booking.choices["visits"]) == 23
        assert booking.acknowledged_visits == []
        assert "MORE" in reply.body and "ANOTHER" not in reply.body
        token = booking.menu_token
        send(f"ANOTHER {token}")
        assert booking.state == "visits" and booking.acknowledged_visits == []
        send(f"MORE {token}")
        session.refresh(booking)
        assert booking.state == "visits"
        assert booking.menu_token != token
        assert booking.acknowledged_visits == []
        while booking.choices["next_cursor"] < len(booking.choices["display"]):
            reply = send(f"MORE {booking.menu_token}")
            assert len(reply.body) <= 2000
            session.refresh(booking)
            assert booking.acknowledged_visits == []
        send(f"ANOTHER {booking.menu_token}")
        session.refresh(booking)
        assert booking.state == "source" and len(booking.acknowledged_visits) == 23
        send(f"{booking.menu_token}:1")
        session.refresh(booking)
        send(f"{booking.menu_token}:1")
        session.refresh(booking)
        send(f"{booking.menu_token}:1")
        session.refresh(booking)
        assert booking.state == "confirmation"
        old_code = booking.menu_token
        existing_id = UUID(booking.acknowledged_visits[0]["id"])
        from dentacircle.services.appointment_service import (
            find_availability,
            reschedule_appointment,
        )

        clinic_row = ClinicDayRepository(session, clinic.clinic_id).get_clinic()
        assert clinic_row is not None
        from zoneinfo import ZoneInfo

        now = datetime.now(UTC)
        future_day = now.astimezone(ZoneInfo(clinic_row.timezone)).date() + timedelta(days=14)
        while True:
            availability = find_availability(
                session,
                clinic.clinic_id,
                clinic.clinician_id,
                clinic.consultation_id,
                future_day,
                now,
            )
            if availability.slots:
                break
            future_day += timedelta(days=1)
        reschedule_appointment(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            existing_id,
            availability.slots[0].starts_at,
            clinic.clinician_id,
            now,
        )
        session.commit()
        send(f"CONFIRM {old_code}")
        session.refresh(booking)
        assert booking.state == "stopped"
        assert session.scalar(select(func.count()).select_from(Appointment)) == 23
        replacement = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.clinic_id == clinic.clinic_id,
                WhatsAppBookingSession.state == "visits",
            )
        )
        assert replacement is not None and replacement.menu_token != old_code


def test_patient_confirms_once_after_selecting_an_earliest_slot(database: str) -> None:
    from sqlalchemy import func

    from dentacircle.models.appointment import Appointment

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )

        def send(body: str) -> Message:
            event_id = str(uuid4())
            receive_message(
                session, clinic.clinic_id, IncomingText("demo", number, event_id, body, None)
            )
            incoming = session.scalar(
                select(Message).where(Message.provider_message_id == event_id)
            )
            assert incoming is not None
            process_action(
                session, resolve_actor(session, authority(clinic.clinic_id), incoming.id)
            )
            session.commit()
            reply = session.scalar(
                select(Message).where(Message.caused_by_message_id == incoming.id)
            )
            assert reply is not None
            return reply

        send("BOOK")
        booking = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.clinic_id == clinic.clinic_id,
            )
        )
        assert booking is not None and booking.state == "source"
        send(f"{booking.menu_token}:1")
        session.refresh(booking)
        assert booking.state == "type"
        send(f"{booking.menu_token}:1")
        session.refresh(booking)
        assert booking.state == "slots"
        send(f"{booking.menu_token}:1")
        session.refresh(booking)
        assert booking.state == "confirmation"
        assert session.scalar(select(func.count()).select_from(Appointment)) == 0
        code = booking.menu_token
        initial_reply = send(f"CONFIRM {code}")
        session.refresh(booking)
        assert booking.state == "booked" and booking.booked_appointment_id is not None
        assert session.scalar(select(func.count()).select_from(Appointment)) == 1
        from dentacircle.services.appointment_service import cancel_appointment
        from dentacircle.services.whatsapp_booking_service import render_queued_reply

        cancel_appointment(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            booking.booked_appointment_id,
            datetime.now(UTC),
        )
        session.commit()
        refreshed = render_queued_reply(session, initial_reply)
        assert refreshed is not None and "cancelled" in refreshed
        assert str(booking.booked_appointment_id)[:8] in refreshed
        repeat = send(f"CONFIRM {code}")
        assert "cancelled" in repeat.body
        assert session.scalar(select(func.count()).select_from(Appointment)) == 1


def test_queued_menu_is_suppressed_when_contact_is_paused(database: str) -> None:
    from dentacircle.services.whatsapp_automation_service import set_staff_automation
    from dentacircle.services.whatsapp_booking_service import render_queued_reply

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )
        receive_message(
            session, clinic.clinic_id, IncomingText("demo", number, "book-event", "BOOK", None)
        )
        incoming = session.scalar(
            select(Message).where(Message.provider_message_id == "book-event")
        )
        assert incoming is not None
        process_action(session, resolve_actor(session, authority(clinic.clinic_id), incoming.id))
        session.commit()
        reply = session.scalar(select(Message).where(Message.caused_by_message_id == incoming.id))
        assert reply is not None and render_queued_reply(session, reply) == reply.body
        set_staff_automation(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "staff_handling",
            "demo",
            {"+15551234567"},
        )
        assert render_queued_reply(session, reply) is None


@pytest.mark.parametrize("source", ["general", "follow-up", "recall"])
def test_booking_only_updates_the_selected_source(database: str, source: str) -> None:
    from sqlalchemy import func

    from dentacircle.models.appointment import Appointment
    from dentacircle.models.follow_up import FollowUp
    from dentacircle.models.recall import Recall

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        old_start = datetime.now(UTC) - timedelta(days=4)
        previous = Appointment(
            id=uuid4(),
            clinic_id=clinic.clinic_id,
            patient_id=clinic.patient_id,
            clinician_user_id=clinic.clinician_id,
            appointment_type_id=clinic.consultation_id,
            starts_at=old_start,
            ends_at=old_start + timedelta(minutes=30),
            status="completed",
        )
        session.add(previous)
        session.flush()
        follow = FollowUp(
            id=uuid4(),
            clinic_id=clinic.clinic_id,
            patient_id=clinic.patient_id,
            status="scheduled",
            due_on=datetime.now(UTC).date(),
        )
        recall = Recall(
            id=uuid4(),
            clinic_id=clinic.clinic_id,
            patient_id=clinic.patient_id,
            appointment_type_id=clinic.consultation_id,
            source_appointment_id=previous.id,
            status="contacted",
            due_on=datetime.now(UTC).date(),
        )
        session.add_all([follow, recall])
        session.commit()
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )

        def send(body: str) -> None:
            event_id = str(uuid4())
            receive_message(
                session, clinic.clinic_id, IncomingText("demo", number, event_id, body, None)
            )
            incoming = session.scalar(
                select(Message).where(Message.provider_message_id == event_id)
            )
            assert incoming is not None
            process_action(
                session, resolve_actor(session, authority(clinic.clinic_id), incoming.id)
            )
            session.commit()

        send("BOOK")
        booking = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.clinic_id == clinic.clinic_id,
            )
        )
        assert booking is not None and booking.state == "source"
        index = {"general": 1, "follow-up": 2, "recall": 3}[source]
        send(f"{booking.menu_token}:{index}")
        session.refresh(booking)
        send(f"{booking.menu_token}:1")
        session.refresh(booking)
        send(f"{booking.menu_token}:1")
        session.refresh(booking)
        assert session.scalar(select(func.count()).select_from(Appointment)) == 1
        send(f"CONFIRM {booking.menu_token}")
        session.refresh(follow)
        session.refresh(recall)
        assert follow.status == ("booked" if source == "follow-up" else "scheduled")
        assert recall.status == ("booked" if source == "recall" else "contacted")
        assert session.scalar(select(func.count()).select_from(Appointment)) == 2


def test_taken_slot_keeps_incoming_message_and_does_not_partially_book(database: str) -> None:
    from sqlalchemy import func

    from dentacircle.models.appointment import Appointment
    from dentacircle.services.appointment_service import book_appointment
    from dentacircle.services.patient_service import register_patient

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )

        def send(body: str) -> Message:
            event_id = str(uuid4())
            receive_message(
                session, clinic.clinic_id, IncomingText("demo", number, event_id, body, None)
            )
            incoming = session.scalar(
                select(Message).where(Message.provider_message_id == event_id)
            )
            assert incoming is not None
            process_action(
                session, resolve_actor(session, authority(clinic.clinic_id), incoming.id)
            )
            session.commit()
            reply = session.scalar(
                select(Message).where(Message.caused_by_message_id == incoming.id)
            )
            assert reply is not None
            return reply

        send("BOOK")
        booking = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.clinic_id == clinic.clinic_id,
            )
        )
        assert booking is not None
        for _ in range(3):
            send(f"{booking.menu_token}:1")
            session.refresh(booking)
        assert booking.state == "confirmation" and booking.appointment_type_id is not None
        assert booking.clinician_user_id is not None
        other = register_patient(
            session, clinic.clinic_id, clinic.actor_id, "Synthetic Other", "9000000011", None
        )
        book_appointment(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            other.id,
            booking.clinician_user_id,
            booking.appointment_type_id,
            datetime.fromisoformat(booking.choices["selected"]["start"]),
            datetime.now(UTC),
        )
        session.commit()
        reply = send(f"CONFIRM {booking.menu_token}")
        assert "no longer available" in reply.body
        assert session.scalar(select(func.count()).select_from(Appointment)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.patient_id == clinic.patient_id)
            )
            == 0
        )


def test_cancelled_acknowledged_visit_is_shown_before_fresh_choice(database: str) -> None:
    from dentacircle.models.appointment import Appointment
    from dentacircle.services.appointment_service import cancel_appointment

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        start = datetime.now(UTC) + timedelta(days=10)
        existing = Appointment(
            id=uuid4(),
            clinic_id=clinic.clinic_id,
            patient_id=clinic.patient_id,
            clinician_user_id=clinic.clinician_id,
            appointment_type_id=clinic.consultation_id,
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
            status="scheduled",
        )
        session.add(existing)
        session.commit()
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )

        def send(body: str) -> Message:
            event_id = str(uuid4())
            receive_message(
                session, clinic.clinic_id, IncomingText("demo", number, event_id, body, None)
            )
            incoming = session.scalar(
                select(Message).where(Message.provider_message_id == event_id)
            )
            assert incoming is not None
            process_action(
                session, resolve_actor(session, authority(clinic.clinic_id), incoming.id)
            )
            session.commit()
            reply = session.scalar(
                select(Message).where(Message.caused_by_message_id == incoming.id)
            )
            assert reply is not None
            return reply

        send("BOOK")
        booking = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.clinic_id == clinic.clinic_id,
            )
        )
        assert booking is not None
        send(f"ANOTHER {booking.menu_token}")
        for _ in range(3):
            session.refresh(booking)
            send(f"{booking.menu_token}:1")
        session.refresh(booking)
        assert booking.state == "confirmation"
        cancel_appointment(
            session, clinic.clinic_id, clinic.actor_id, existing.id, datetime.now(UTC)
        )
        session.commit()
        reply = send(f"CONFIRM {booking.menu_token}")
        assert "cancelled" in reply.body and "Appointment" in reply.body
        assert str(existing.id) not in reply.body
        assert "CONTINUE" in reply.body
        assert booking.booked_appointment_id is None


def test_welcome_is_not_sent_after_staff_takeover(database: str) -> None:
    from dentacircle.services.whatsapp_automation_service import set_staff_automation
    from dentacircle.services.whatsapp_booking_service import render_queued_reply

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )
        receive_message(
            session, clinic.clinic_id, IncomingText("demo", number, "greeting", "HI", None)
        )
        incoming = session.scalar(select(Message).where(Message.provider_message_id == "greeting"))
        assert incoming is not None
        process_action(session, resolve_actor(session, authority(clinic.clinic_id), incoming.id))
        session.commit()
        reply = session.scalar(select(Message).where(Message.caused_by_message_id == incoming.id))
        assert reply is not None and render_queued_reply(session, reply) == reply.body
        set_staff_automation(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "staff_handling",
            "demo",
            {number},
        )
        assert render_queued_reply(session, reply) is None


def test_slot_pages_are_ordered_and_date_and_clinician_filters_refresh_codes(database: str) -> None:
    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )

        def send(body: str) -> Message:
            event_id = str(uuid4())
            receive_message(
                session, clinic.clinic_id, IncomingText("demo", number, event_id, body, None)
            )
            incoming = session.scalar(
                select(Message).where(Message.provider_message_id == event_id)
            )
            assert incoming is not None
            process_action(
                session, resolve_actor(session, authority(clinic.clinic_id), incoming.id)
            )
            session.commit()
            reply = session.scalar(
                select(Message).where(Message.caused_by_message_id == incoming.id)
            )
            assert reply is not None and len(reply.body) <= 2000
            return reply

        send("BOOK")
        booking = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.clinic_id == clinic.clinic_id,
            )
        )
        assert booking is not None
        for _ in range(2):
            send(f"{booking.menu_token}:1")
            session.refresh(booking)
        assert booking.state == "slots"
        entries = booking.choices["entries"]
        assert len(entries) > 5
        assert [(item["start"], item["id"]) for item in entries] == sorted(
            (item["start"], item["id"]) for item in entries
        )
        old = booking.menu_token
        send(f"MORE {old}")
        session.refresh(booking)
        assert booking.menu_token != old and booking.choices["cursor"] == 5
        send(f"CLINICIANS {booking.menu_token}")
        session.refresh(booking)
        assert booking.choices["title"] == "Choose a clinician"
        send(f"{booking.menu_token}:1")
        session.refresh(booking)
        assert len({item["id"] for item in booking.choices["entries"]}) <= 1
        chosen_day = booking.choices["entries"][0]["start"][:10]
        send(f"DATE {chosen_day} {booking.menu_token}")
        session.refresh(booking)
        assert all(item["start"].startswith(chosen_day) for item in booking.choices["entries"])
        reply = send(f"{old}:1")
        assert "invalid" in reply.body.lower() and booking.state == "slots"


def test_concurrent_confirmations_create_one_visit(database: str) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import func

    from dentacircle.models.appointment import Appointment

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )

        def prepare(body: str) -> UUID:
            event_id = str(uuid4())
            receive_message(
                session, clinic.clinic_id, IncomingText("demo", number, event_id, body, None)
            )
            incoming = session.scalar(
                select(Message).where(Message.provider_message_id == event_id)
            )
            assert incoming is not None
            return incoming.id

        incoming_id = prepare("BOOK")
        process_action(session, resolve_actor(session, authority(clinic.clinic_id), incoming_id))
        session.commit()
        booking = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.clinic_id == clinic.clinic_id,
            )
        )
        assert booking is not None
        for _ in range(3):
            incoming_id = prepare(f"{booking.menu_token}:1")
            process_action(
                session, resolve_actor(session, authority(clinic.clinic_id), incoming_id)
            )
            session.commit()
            session.refresh(booking)
        assert booking.state == "confirmation"
        first = prepare(f"CONFIRM {booking.menu_token}")
        second = prepare(f"CONFIRM {booking.menu_token}")
    barrier = Barrier(2)

    def confirm(message_id: UUID) -> None:
        with Session(get_engine()) as separate:
            actor = resolve_actor(separate, authority(clinic.clinic_id), message_id)
            barrier.wait(timeout=5)
            process_action(separate, actor)
            separate.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(confirm, message_id) for message_id in (first, second)]
        for job in jobs:
            job.result(timeout=15)
    with Session(get_engine()) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(
                    Appointment.clinic_id == clinic.clinic_id,
                    Appointment.patient_id == clinic.patient_id,
                )
            )
            == 1
        )


def test_resume_challenge_cannot_be_used_by_another_linked_contact(database: str) -> None:
    from dentacircle.services.patient_service import register_patient

    clinic = world()
    first_number, second_number = "+15551234567", "+15551234568"
    numbers = {first_number, second_number}
    credentials = authority(clinic.clinic_id, numbers=",".join(sorted(numbers)))
    with Session(get_engine(), expire_on_commit=False) as session:
        other = register_patient(
            session, clinic.clinic_id, clinic.actor_id, "Synthetic Other", "9000000011", None
        )
        session.commit()
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            first_number,
            numbers,
        )
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, other.id, "demo", second_number, numbers
        )

        def send(number: str, body: str) -> None:
            event_id = str(uuid4())
            receive_message(
                session, clinic.clinic_id, IncomingText("demo", number, event_id, body, None)
            )
            message = session.scalar(select(Message).where(Message.provider_message_id == event_id))
            assert message is not None
            process_action(session, resolve_actor(session, credentials, message.id))
            session.commit()

        send(first_number, "STOP")
        send(second_number, "STOP")
        send(first_number, "BOOK")
        challenge = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.clinic_id == clinic.clinic_id,
                WhatsAppBookingSession.state == "resume_challenge",
            )
        )
        assert challenge is not None
        send(second_number, f"BOOK {challenge.menu_token}")
        contact = MessagingRepository(session, clinic.clinic_id).contact_for_patient(other.id)
        assert contact is not None and contact.automation_state == "stopped"
