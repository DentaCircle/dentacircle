"""Staff control is durable and replaying a send does not retake a chat."""

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.repositories.messaging_repository import MessagingRepository
from dentacircle.services.messaging_service import link_contact, send_message
from dentacircle.services.whatsapp_automation_service import (
    AutomationConflict,
    set_staff_automation,
)
from tests.test_messaging_service import FakeProvider
from tests.timeline_support import world

pytest_plugins = ["tests.timeline_support"]


def test_staff_message_takes_over_once_even_after_resume(database: str) -> None:
    clinic = world()
    request_id = uuid4()
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
        provider = FakeProvider()
        args = (
            session,
            provider,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "Hello",
            request_id,
            "demo",
            {"+15551234567"},
        )
        send_message(*args)
        contact = MessagingRepository(session, clinic.clinic_id).contact_for_patient(
            clinic.patient_id
        )
        assert contact is not None and contact.automation_state == "staff_handling"
        set_staff_automation(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "active",
            "demo",
            {"+15551234567"},
        )
        version = contact.automation_version
        _, created = send_message(*args)
        session.refresh(contact)
        assert not created
        assert contact.automation_state == "active" and contact.automation_version == version


def test_inactive_patient_cannot_resume(database: str) -> None:
    from dentacircle.models.patient import Patient

    clinic = world()
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
        patient = session.get(Patient, clinic.patient_id)
        assert patient is not None
        patient.status = "inactive"
        session.commit()
        with pytest.raises(AutomationConflict):
            set_staff_automation(
                session,
                clinic.clinic_id,
                clinic.actor_id,
                clinic.patient_id,
                "active",
                "demo",
                {"+15551234567"},
            )


def test_invitation_does_not_take_over_and_purpose_is_part_of_replay(database: str) -> None:
    from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
    from dentacircle.services.messaging_service import ContactConflict, invitation_text

    clinic = world()
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "demo",
            "+15551234567",
            {"+15551234567"},
        )
        clinic_row = ClinicDayRepository(session, clinic.clinic_id).get_clinic()
        assert clinic_row is not None
        body = invitation_text(clinic_row.name)
        request_id = uuid4()
        provider = FakeProvider()
        args = (
            session,
            provider,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            body,
            request_id,
            "demo",
            {"+15551234567"},
        )
        _, created = send_message(*args, purpose="booking_invitation")
        contact = MessagingRepository(session, clinic.clinic_id).contact_for_patient(
            clinic.patient_id
        )
        assert created and contact is not None and contact.automation_state == "active"
        _, created = send_message(*args, purpose="booking_invitation")
        assert not created
        with pytest.raises(ContactConflict):
            send_message(*args, purpose="chat")
        with pytest.raises(ContactConflict):
            send_message(
                *args[:-4],
                "not the preview",
                uuid4(),
                "demo",
                {"+15551234567"},
                purpose="booking_invitation",
            )


def test_replaying_staff_send_after_patient_resume_does_not_take_over(database: str) -> None:
    from sqlalchemy import select

    from dentacircle.integrations.messaging.base import IncomingText
    from dentacircle.models.messaging import Message
    from dentacircle.models.whatsapp_booking_session import WhatsAppBookingSession
    from dentacircle.services.messaging_service import receive_message
    from dentacircle.services.whatsapp_actor import resolve_actor
    from dentacircle.services.whatsapp_booking_service import process_action
    from tests.test_whatsapp_actor import authority

    clinic = world()
    number = "+15551234567"
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(
            session, clinic.clinic_id, clinic.actor_id, clinic.patient_id, "demo", number, {number}
        )
        request = uuid4()
        provider = FakeProvider()
        args = (
            session,
            provider,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            "Staff reply",
            request,
            "demo",
            {number},
        )
        send_message(*args)

        def incoming(body: str) -> None:
            event_id = str(uuid4())
            receive_message(
                session, clinic.clinic_id, IncomingText("demo", number, event_id, body, None)
            )
            row = session.scalar(select(Message).where(Message.provider_message_id == event_id))
            assert row is not None
            process_action(session, resolve_actor(session, authority(clinic.clinic_id), row.id))
            session.commit()

        incoming("BOOK")
        challenge = session.scalar(
            select(WhatsAppBookingSession).where(
                WhatsAppBookingSession.clinic_id == clinic.clinic_id,
                WhatsAppBookingSession.state == "resume_challenge",
            )
        )
        assert challenge is not None
        incoming(f"BOOK {challenge.menu_token}")
        contact = MessagingRepository(session, clinic.clinic_id).contact_for_patient(
            clinic.patient_id
        )
        assert contact is not None and contact.automation_state == "active"
        version = contact.automation_version
        _, created = send_message(*args)
        session.refresh(contact)
        assert not created and contact.automation_state == "active"
        assert contact.automation_version == version
