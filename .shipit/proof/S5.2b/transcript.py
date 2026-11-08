"""Exercise the booking paths with a fake provider in the synthetic proof database."""

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from dentacircle.core.config import Settings
from dentacircle.core.database import get_engine
from dentacircle.integrations.messaging.base import Connection, IncomingText
from dentacircle.models.messaging import Message
from dentacircle.models.whatsapp_booking_session import WhatsAppBookingSession
from dentacircle.services.follow_up_service import create_manual_follow_up
from dentacircle.services.messaging_service import (
    invitation_text,
    link_contact,
    receive_event,
    send_message,
)
from dentacircle.services.patient_service import register_patient
from dentacircle.services.whatsapp_actor import authenticate_callback
from dentacircle.services.whatsapp_automation_service import set_staff_automation
from dentacircle.services.whatsapp_booking_service import process_action
from sqlalchemy import select
from sqlalchemy.orm import Session


class FakeProvider:
    def connection(self) -> Connection:
        return Connection("connected", True)

    def send_text(self, number: str, body: str, *, fence_fd: int | None = None) -> str:
        return "accepted"

    def normalize_event(self, payload: object) -> IncomingText | None:
        assert isinstance(payload, IncomingText)
        return payload


def safe(body: str) -> str:
    return re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f-]{27}\b", "[visit reference]", body, flags=re.IGNORECASE
    )


def main() -> None:
    metadata = json.loads(Path("../../.openwa/proof.json").read_text())
    os.environ["DATABASE_URL"] = metadata["database_url"]
    clinic, patient, staff = (
        UUID(metadata[key]) for key in ("clinic_id", "patient_id", "staff_id")
    )
    numbers = {"+15551234567", "+15551234568"}
    settings = Settings(
        database_url=metadata["database_url"],
        messaging_clinic_id=str(clinic),
        messaging_account="demo",
        messaging_callback_secret="synthetic-secret",
        messaging_allowlist=",".join(numbers),
        _env_file=None,
    )
    authority = authenticate_callback("synthetic-secret", settings)
    provider = FakeProvider()
    transcript: list[dict[str, str]] = []
    with Session(get_engine(), expire_on_commit=False) as session:
        link_contact(session, clinic, staff, patient, "demo", "+15551234567", numbers)

        def send(number: str, body: str) -> None:
            event = IncomingText("demo", number, str(uuid4()), body, None)
            receive_event(session, authority, provider, event, process_action)  # type: ignore[arg-type]
            incoming = session.scalar(
                select(Message).where(
                    Message.provider_message_id == event.provider_message_id
                )
            )
            assert incoming is not None
            reply = session.scalar(
                select(Message).where(Message.caused_by_message_id == incoming.id)
            )
            transcript.append({"from": "patient", "text": safe(body)})
            if reply is not None:
                transcript.append({"from": "clinic", "text": safe(reply.body)})

        def current() -> WhatsAppBookingSession:
            row = session.scalar(
                select(WhatsAppBookingSession)
                .where(
                    WhatsAppBookingSession.clinic_id == clinic,
                    WhatsAppBookingSession.state.in_(
                        (
                            "visits",
                            "source",
                            "type",
                            "slots",
                            "confirmation",
                            "resume_challenge",
                        )
                    ),
                )
                .order_by(WhatsAppBookingSession.created_at.desc())
                .limit(1)
            )
            assert row is not None
            return row

        send("+15551234567", "HI")
        send("+15551234567", "BOOK")
        send("+15551234567", f"ANOTHER {current().menu_token}")
        for _ in range(3):
            send("+15551234567", f"{current().menu_token}:1")
        send("+15551234567", f"CONFIRM {current().menu_token}")
        send("+15551234567", "STATUS")
        send("+15551234567", "STOP")
        send("+15551234567", "BOOK")
        send("+15551234567", f"BOOK {current().menu_token}")
        send("+15551234567", "STAFF")
        set_staff_automation(
            session, clinic, staff, patient, "staff_handling", "demo", numbers
        )
        set_staff_automation(session, clinic, staff, patient, "active", "demo", numbers)
        send("+15551234567", "STAFF")

        other = register_patient(
            session, clinic, staff, "Synthetic Invitation Patient", "9000000002", None
        )
        session.commit()
        link_contact(session, clinic, staff, other.id, "demo", "+15551234568", numbers)
        invitation = invitation_text("Synthetic Demo Clinic")
        send_message(
            session,
            provider,
            clinic,
            staff,
            other.id,
            invitation,
            uuid4(),
            "demo",
            numbers,
            purpose="booking_invitation",
        )  # type: ignore[arg-type]
        transcript.append({"from": "staff invitation", "text": invitation})
        now = datetime.now(UTC)
        create_manual_follow_up(
            session,
            clinic,
            staff,
            other.id,
            now.astimezone(ZoneInfo("Asia/Kolkata")).date(),
            now,
        )
        session.commit()
        send("+15551234568", "BOOK")
        send("+15551234568", f"{current().menu_token}:2")
        for _ in range(2):
            send("+15551234568", f"{current().menu_token}:1")
        send("+15551234568", f"CONFIRM {current().menu_token}")
        Path("../../.openwa/proof-patients.json").write_text(
            json.dumps(
                {"patient_id": str(patient), "invited_patient_id": str(other.id)}
            )
        )
    Path("../../.shipit/proof/S5.2b/samples.json").write_text(
        json.dumps(transcript, indent=2) + "\n"
    )
    print("Synthetic transcript is ready; no provider messages were sent.")


if __name__ == "__main__":
    main()
