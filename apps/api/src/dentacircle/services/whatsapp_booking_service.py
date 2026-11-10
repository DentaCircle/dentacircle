"""Deterministic patient booking controls, using the verified message identity."""

import re
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.domain.appointment import AppointmentFieldError
from dentacircle.domain.whatsapp_booking import menu_page, parse_menu_command
from dentacircle.models.messaging import Message, MessagingContact
from dentacircle.models.whatsapp_booking_session import WhatsAppBookingSession
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.messaging_repository import MessagingRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.repositories.whatsapp_booking_repository import WhatsAppBookingRepository
from dentacircle.services.appointment_service import (
    book_appointment,
    find_availability,
)
from dentacircle.services.automatic_reply_service import queue_reply
from dentacircle.services.follow_up_service import book_follow_up
from dentacircle.services.recall_service import book_recall
from dentacircle.services.whatsapp_actor import WhatsAppActor, require_patient
from dentacircle.services.whatsapp_automation_service import transition

_ACTIVE = ("resume_challenge", "visits", "source", "type", "slots", "confirmation")
_HANDOFF = (
    "Reception can review your message. Clinical questions need a clinician. "
    "Reply BOOK to request booking again."
)


def _current(
    session: Session, actor: WhatsAppActor, contact: MessagingContact
) -> WhatsAppBookingSession | None:
    return session.scalar(
        select(WhatsAppBookingSession)
        .where(
            WhatsAppBookingSession.clinic_id == actor.clinic_id,
            WhatsAppBookingSession.contact_id == contact.id,
            WhatsAppBookingSession.account_key == actor.account_key,
            WhatsAppBookingSession.state.in_(_ACTIVE),
        )
        .with_for_update()
    )


def _new_session(
    session: Session, actor: WhatsAppActor, contact: MessagingContact, state: str, now: datetime
) -> WhatsAppBookingSession:
    booking = WhatsAppBookingSession(
        id=uuid4(),
        clinic_id=actor.clinic_id,
        contact_id=contact.id,
        account_key=actor.account_key,
        state=state,
        menu_version=1,
        menu_token=secrets.token_hex(4).upper(),
        automation_version=contact.automation_version,
        choices={},
        acknowledged_visits=[],
        expires_at=now + timedelta(minutes=15),
    )
    session.add(booking)
    session.flush()
    return booking


def _matches_current_prompt(
    session: Session,
    actor: WhatsAppActor,
    contact: MessagingContact,
    booking: WhatsAppBookingSession,
) -> bool:
    """Only a verified reply to this contact's current accepted prompt can select."""
    quoted = actor.quoted_stanza_id
    if quoted is None or booking.automation_version != contact.automation_version:
        return False
    rows = session.scalars(
        select(Message).where(
            Message.clinic_id == actor.clinic_id,
            Message.contact_id == contact.id,
            Message.account_key == actor.account_key,
            Message.origin == "automation",
            Message.state == "accepted",
            Message.booking_session_id == booking.id,
            Message.menu_version == booking.menu_version,
            Message.automation_version == booking.automation_version,
            Message.reply_kind.in_(("menu", "resume_challenge")),
            Message.provider_message_id.is_not(None),
        )
    ).all()
    matches = [
        row
        for row in rows
        if row.provider_message_id is not None
        and row.provider_message_id.rsplit("_", 1)[-1] == quoted
    ]
    return len(matches) == 1


def _quoted_command(booking: WhatsAppBookingSession, command: str) -> str:
    """Translate a reply only after its prompt has been authenticated."""
    token = booking.menu_token
    number = command.replace("\ufe0f", "").replace("\u20e3", "")
    if booking.state == "resume_challenge" and number == "1":
        return f"BOOK {token}"
    if booking.state == "visits" and number == "1":
        if booking.choices["next_cursor"] < len(booking.choices["display"]):
            return f"MORE {token}"
        return f"{'ANOTHER' if booking.choices['visits'] else 'CONTINUE'} {token}"
    if booking.state == "confirmation":
        return {"1": f"CONFIRM {token}", "2": f"TIMES {token}", "3": f"TYPE {token}"}.get(
            number, command
        )
    if booking.state in ("source", "type", "slots"):
        if number.isdigit():
            return f"{token}:{number}"
        if command in ("MORE", "TYPE", "CLINICIANS"):
            return f"{command} {token}"
        if booking.state == "slots" and command.startswith("DATE "):
            return f"{command} {token}"
    return command


def process_action(session: Session, actor: WhatsAppActor) -> None:
    """Apply one authenticated inbound message within the callback transaction."""
    patient = PatientRepository(session, actor.clinic_id).get(actor.patient_id, lock=True)
    if patient is None or patient.status != "active":
        return
    require_patient(session, actor, actor.clinic_id, actor.patient_id)
    contact = MessagingRepository(session, actor.clinic_id).contact_for_patient(
        actor.patient_id, lock=True
    )
    incoming = session.scalar(
        select(Message).where(Message.clinic_id == actor.clinic_id, Message.id == actor.message_id)
    )
    if contact is None or incoming is None or incoming.contact_id != contact.id:
        return
    now = datetime.now(UTC)
    command = incoming.body.strip().upper().replace("\ufe0f", "").replace("\u20e3", "")
    booking = _current(session, actor, contact)
    if command == "STATUS" or command.startswith("CONFIRM "):
        query = select(WhatsAppBookingSession).where(
            WhatsAppBookingSession.clinic_id == actor.clinic_id,
            WhatsAppBookingSession.contact_id == contact.id,
            WhatsAppBookingSession.account_key == actor.account_key,
            WhatsAppBookingSession.state == "booked",
        )
        if command != "STATUS":
            query = query.where(WhatsAppBookingSession.menu_token == command[8:].strip())
        saved = session.scalar(query.order_by(WhatsAppBookingSession.created_at.desc()).limit(1))
        if saved is not None:
            queue_reply(
                session,
                actor,
                _result_text(session, actor, saved, now),
                booking=saved,
                kind="result",
            )
            return
        if command == "STATUS":
            queue_reply(
                session, actor, "No booking result is available. Reply STAFF for reception."
            )
            return
    if booking is not None and booking.expires_at <= now:
        booking.state = "expired"
        session.flush()
        booking = None
    if booking is not None and _matches_current_prompt(session, actor, contact, booking):
        command = _quoted_command(booking, command)
    if command in ("STOP", "STAFF", "TALK TO RECEPTION"):
        state: Literal["stopped", "needs_staff"] = "stopped" if command == "STOP" else "needs_staff"
        transition(session, actor.clinic_id, contact, actor, state)
        queue_reply(
            session,
            actor,
            "Booking stopped. Your appointments are unchanged." if state == "stopped" else _HANDOFF,
        )
        return
    if contact.automation_state != "active":
        if command == "BOOK":
            if booking is None or booking.state != "resume_challenge":
                booking = _new_session(session, actor, contact, "resume_challenge", now)
            queue_reply(
                session,
                actor,
                "To resume booking, reply to this message with 1\ufe0f\u20e3 within 15 minutes.",
                booking=booking,
                kind="resume_challenge",
            )
        elif command.startswith("BOOK "):
            if (
                booking is not None
                and booking.state == "resume_challenge"
                and command == f"BOOK {booking.menu_token}"
                and booking.automation_version == contact.automation_version
            ):
                transition(session, actor.clinic_id, contact, actor, "active")
                _start(session, actor, contact, now)
            else:
                queue_reply(
                    session, actor, "That reply is no longer valid. Send BOOK to start again."
                )
        return
    if (
        booking is not None
        and booking.state == "visits"
        and _visit_command(session, actor, contact, booking, command, now)
    ):
        return
    if booking is not None and booking.state in ("source", "type", "slots", "confirmation"):
        try:
            if _choice_command(session, actor, contact, booking, command, now):
                return
        except AppointmentFieldError:
            previous = booking.acknowledged_visits
            booking.state = "stopped"
            session.flush()
            _start(
                session,
                actor,
                contact,
                now,
                previous,
                "Those choices changed. Please review again.",
            )
            return
    if command == "BOOK" or command == "START OVER":
        if booking is None or command == "START OVER":
            if booking is not None:
                booking.state = "stopped"
                session.flush()
            _start(session, actor, contact, now)
        else:
            _rotate(booking, now)
            _resume_menu(session, actor, booking)
    elif (
        command.startswith(("CONFIRM", "MORE", "ANOTHER", "BOOK ", "DATE ", "TYPE ", "CLINICIANS "))
        or command.isdigit()
        or re.fullmatch(r"[A-Z0-9]+:\d+", command)
    ):
        queue_reply(
            session,
            actor,
            "That choice is invalid. Reply to the latest message or send STAFF for help.",
        )
    elif command in ("HI", "HELLO", "HEY"):
        queue_reply(
            session,
            actor,
            "Welcome. Reply BOOK to choose an appointment or STAFF for reception.",
            kind="menu",
            standalone_version=contact.automation_version,
        )
    elif command == "HELP":
        queue_reply(
            session,
            actor,
            "Reply BOOK to book, STAFF for reception, or STOP to pause booking.",
            kind="menu",
            standalone_version=contact.automation_version,
        )
    elif booking is not None and command not in ("THANKS", "THANK YOU"):
        transition(session, actor.clinic_id, contact, actor, "needs_staff")
        queue_reply(session, actor, _HANDOFF)


def _resume_menu(session: Session, actor: WhatsAppActor, booking: WhatsAppBookingSession) -> None:
    if booking.state == "visits":
        _show_visits(session, actor, booking)
    elif booking.state in ("source", "type", "slots"):
        _show_options(
            session,
            actor,
            booking,
            booking.choices["entries"],
            booking.choices["title"],
            booking.choices["cursor"],
        )
    elif booking.state == "confirmation":
        choice = booking.choices["selected"]
        kind = next(
            (
                item["label"]
                for item in _all_types(session, actor)
                if item["id"] == str(booking.appointment_type_id)
            ),
            "Appointment",
        )
        queue_reply(
            session,
            actor,
            f"*Please check your appointment*\n\n{kind}\n{choice['label']}\n\n"
            "Your appointment is not reserved yet.\n\n"
            "1\ufe0f\u20e3 Confirm booking\n2\ufe0f\u20e3 Change time\n"
            "3\ufe0f\u20e3 Change appointment type\n\n"
            "Use WhatsApp Reply on this message, then send your choice.",
            booking=booking,
            kind="menu",
        )


def _visit_snapshot(session: Session, actor: WhatsAppActor, now: datetime) -> list[dict[str, str]]:
    repo = AppointmentRepository(session, actor.clinic_id)
    cursor: tuple[datetime, UUID] | None = None
    result: list[dict[str, str]] = []
    while True:
        rows = repo.booking_upcoming_page(actor.patient_id, now, cursor)
        if not rows:
            return result
        for visit, _, clinician, kind in rows:
            result.append(
                {
                    "id": str(visit.id),
                    "starts_at": visit.starts_at.isoformat(),
                    "ends_at": visit.ends_at.isoformat(),
                    "clinician_id": str(visit.clinician_user_id),
                    "type_id": str(visit.appointment_type_id),
                    "status": visit.status,
                    "clinician_name": clinician.full_name,
                    "type_name": kind.name,
                }
            )
        last = rows[-1][0]
        cursor = last.starts_at, last.id


def _rotate(booking: WhatsAppBookingSession, now: datetime) -> None:
    booking.menu_version += 1
    booking.menu_token = secrets.token_hex(4).upper()
    booking.expires_at = now + timedelta(minutes=15)
    booking.updated_at = now


def _show_visits(
    session: Session, actor: WhatsAppActor, booking: WhatsAppBookingSession, notice: str = ""
) -> None:
    clinic = ClinicDayRepository(session, actor.clinic_id).get_clinic()
    if clinic is None:
        raise RuntimeError("clinic not found")
    zone = ZoneInfo(clinic.timezone)
    visits = booking.choices["visits"]
    display = booking.choices["display"]
    cursor = booking.choices["cursor"]
    lines = [notice, "", "*Your appointments*"] if notice else ["*Your appointments*"]
    for index, visit in enumerate(display[cursor : cursor + 5], start=cursor + 1):
        start = datetime.fromisoformat(visit["starts_at"]).astimezone(zone)
        name = " ".join(visit["type_name"].split())[:150]
        clinician = " ".join(visit["clinician_name"].split())[:150]
        lines.append(
            f"\nAppointment {index}\n"
            f"{start:%d %b %Y} at {start:%H:%M}\n"
            f"{name} with {clinician}\nStatus: {visit['status']}"
        )
    next_cursor = min(cursor + 5, len(display))
    booking.choices = {
        "visits": visits,
        "display": display,
        "cursor": cursor,
        "next_cursor": next_cursor,
    }
    lines.append("")
    if next_cursor < len(display):
        lines.append("1\ufe0f\u20e3 See more appointments")
    elif visits:
        lines.append("1\ufe0f\u20e3 Book another visit")
    else:
        lines.append("1\ufe0f\u20e3 Continue")
    lines.extend(
        ["", "Use WhatsApp Reply on this message, then send 1.", "", "Need help? Reply STAFF."]
    )
    queue_reply(session, actor, "\n".join(lines), booking=booking, kind="menu")


def _show_source(
    session: Session, actor: WhatsAppActor, booking: WhatsAppBookingSession, notice: str = ""
) -> None:
    booking.state = "source"
    entries = [{"id": "general", "label": "General visit"}]
    for name, source_id, due in WhatsAppBookingRepository(session, actor.clinic_id).sources(
        actor.patient_id
    ):
        entries.append({"id": str(source_id), "kind": name.lower(), "label": f"{name} due {due}"})
    title = f"{notice} Choose a booking source" if notice else "Choose a booking source"
    _show_options(session, actor, booking, entries, title, 0)


def _show_options(
    session: Session,
    actor: WhatsAppActor,
    booking: WhatsAppBookingSession,
    entries: list[dict[str, str]],
    title: str,
    cursor: int,
) -> None:
    page = menu_page(title, [entry["label"] for entry in entries], cursor, booking.menu_token)
    booking.choices = {
        "entries": entries,
        "title": title,
        "cursor": cursor,
        "next_cursor": page.next_cursor,
        "count": len(page.entries),
    }
    queue_reply(session, actor, page.text, booking=booking, kind="menu")


def _all_types(session: Session, actor: WhatsAppActor) -> list[dict[str, str]]:
    repo = WhatsAppBookingRepository(session, actor.clinic_id)
    result: list[dict[str, str]] = []
    cursor = None
    while rows := repo.type_page(cursor):
        result.extend({"id": str(row.id), "label": row.name} for row in rows)
        cursor = rows[-1].id
    return result


def _all_clinicians(session: Session, actor: WhatsAppActor) -> list[dict[str, str]]:
    repo = WhatsAppBookingRepository(session, actor.clinic_id)
    result: list[dict[str, str]] = []
    cursor = None
    while rows := repo.clinician_page(cursor):
        result.extend({"id": str(row.id), "label": row.full_name} for row in rows)
        cursor = rows[-1].id
    return result


def _offer_types(session: Session, actor: WhatsAppActor, booking: WhatsAppBookingSession) -> None:
    booking.state = "type"
    entries = _all_types(session, actor)
    entries.append({"id": "unsure", "label": "Not sure what to book"})
    _show_options(session, actor, booking, entries, "Choose an appointment type", 0)


def _offer_dates(
    session: Session, actor: WhatsAppActor, booking: WhatsAppBookingSession, now: datetime
) -> None:
    clinic = ClinicDayRepository(session, actor.clinic_id).get_clinic()
    if clinic is None:
        raise RuntimeError("clinic not found")
    today = now.astimezone(ZoneInfo(clinic.timezone)).date()
    entries = [{"id": "earliest", "label": "Earliest available"}]
    entries.extend(
        {"id": day.isoformat(), "label": day.strftime("%a, %d %b")}
        for day in (today + timedelta(days=i) for i in range(7))
    )
    booking.state = "slots"
    _show_options(session, actor, booking, entries, "Choose a date", 0)


def _offer_clinicians(
    session: Session, actor: WhatsAppActor, booking: WhatsAppBookingSession
) -> None:
    entries = [{"id": "any", "label": "Any available clinician"}, *_all_clinicians(session, actor)]
    booking.state = "slots"
    _show_options(session, actor, booking, entries, "Choose a clinician", 0)


def _offer_slots(
    session: Session,
    actor: WhatsAppActor,
    booking: WhatsAppBookingSession,
    now: datetime,
    chosen_day: date | None = None,
    chosen_clinician: UUID | None = None,
) -> None:
    all_entries = _slot_entries(session, actor, booking, now, chosen_day, chosen_clinician)
    booking.state = "slots"
    if not all_entries:
        title = "No slots found."
    else:
        title = "Choose an available time."
    title += (
        "\nTo change date, reply DATE YYYY-MM-DD.\n"
        "For another clinician, reply CLINICIANS.\nTo change type, reply TYPE."
    )
    _show_options(session, actor, booking, all_entries, title, 0)


def _slot_entries(
    session: Session,
    actor: WhatsAppActor,
    booking: WhatsAppBookingSession,
    now: datetime,
    chosen_day: date | None,
    chosen_clinician: UUID | None,
) -> list[dict[str, str]]:
    clinic = ClinicDayRepository(session, actor.clinic_id).get_clinic()
    if clinic is None or booking.appointment_type_id is None:
        raise RuntimeError("booking configuration is missing")
    zone = ZoneInfo(clinic.timezone)
    first_day = chosen_day or now.astimezone(zone).date()
    days = [first_day + timedelta(days=i) for i in range(1 if chosen_day else 7)]
    all_entries: list[dict[str, str]] = []
    repo = AppointmentRepository(session, actor.clinic_id)
    for clinician in _all_clinicians(session, actor):
        clinician_id = UUID(clinician["id"])
        if chosen_clinician is not None and clinician_id != chosen_clinician:
            continue
        for day in days:
            available = find_availability(
                session, actor.clinic_id, clinician_id, booking.appointment_type_id, day, now
            )
            for slot in available.slots:
                if repo.busy_spans(
                    span_start=slot.starts_at, span_end=slot.ends_at, patient_id=actor.patient_id
                ):
                    continue
                all_entries.append(
                    {
                        "id": clinician["id"],
                        "clinician": clinician["label"],
                        "start": slot.starts_at.isoformat(),
                        "end": slot.ends_at.isoformat(),
                        "label": (
                            f"{slot.starts_at:%Y-%m-%d %H:%M}–{slot.ends_at:%H:%M} "
                            f"{clinic.timezone} · {clinician['label']}"
                        ),
                    }
                )
    all_entries.sort(key=lambda entry: (entry["start"], entry["id"]))
    return all_entries


def _choice_command(
    session: Session,
    actor: WhatsAppActor,
    contact: MessagingContact,
    booking: WhatsAppBookingSession,
    command: str,
    now: datetime,
) -> bool:
    if command in ("BOOK", "START OVER", "HELP", "STOP", "STAFF", "TALK TO RECEPTION"):
        return False
    if booking.state == "confirmation" and command == f"TYPE {booking.menu_token}":
        _rotate(booking, now)
        _offer_types(session, actor, booking)
        return True
    if booking.state == "confirmation" and command == f"TIMES {booking.menu_token}":
        booking.clinician_user_id = None
        booking.selected_date = None
        _rotate(booking, now)
        _offer_slots(session, actor, booking, now)
        return True
    if booking.state == "confirmation":
        if command.startswith("CONFIRM"):
            if command == f"CONFIRM {booking.menu_token}":
                _confirm(session, actor, contact, booking, now)
            else:
                queue_reply(
                    session, actor, "That confirmation is invalid. Send BOOK or STAFF for help."
                )
            return True
        return False
    if booking.state == "slots" and command.startswith("DATE "):
        parts = command.split()
        clinic = ClinicDayRepository(session, actor.clinic_id).get_clinic()
        try:
            if len(parts) != 3 or parts[2] != booking.menu_token or clinic is None:
                raise ValueError
            chosen = date.fromisoformat(parts[1])
            today = now.astimezone(ZoneInfo(clinic.timezone)).date()
            if not today <= chosen <= today + timedelta(days=365):
                raise ValueError
        except ValueError:
            queue_reply(
                session, actor, "That date or reply is invalid. Send BOOK or STAFF for help."
            )
            return True
        booking.selected_date = chosen
        _rotate(booking, now)
        _offer_slots(session, actor, booking, now, chosen, booking.clinician_user_id)
        return True
    if booking.state == "slots" and command == f"CLINICIANS {booking.menu_token}":
        _rotate(booking, now)
        _offer_clinicians(session, actor, booking)
        return True
    if command == f"TYPE {booking.menu_token}":
        _rotate(booking, now)
        _offer_types(session, actor, booking)
        return True
    if command.startswith("MORE ") and command == f"MORE {booking.menu_token}":
        entries = booking.choices["entries"]
        if booking.state == "type":
            current = _all_types(session, actor) + [
                {"id": "unsure", "label": "Not sure what to book"}
            ]
        elif booking.state == "slots" and booking.choices["title"] == "Choose a clinician":
            current = [
                {"id": "any", "label": "Any available clinician"},
                *_all_clinicians(session, actor),
            ]
        elif booking.state == "slots" and booking.choices["title"] == "Choose a date":
            current = entries
        elif booking.state == "slots":
            current = _slot_entries(
                session, actor, booking, now, booking.selected_date, booking.clinician_user_id
            )
        else:
            current = entries
        if current != entries:
            _rotate(booking, now)
            if booking.state == "type":
                _offer_types(session, actor, booking)
            elif booking.choices["title"] == "Choose a clinician":
                _show_options(session, actor, booking, current, "Choose a clinician", 0)
            else:
                _offer_slots(
                    session, actor, booking, now, booking.selected_date, booking.clinician_user_id
                )
            return True
    if booking.state == "source":
        fresh = [{"id": "general", "label": "General visit"}]
        for name, source_id, due in WhatsAppBookingRepository(session, actor.clinic_id).sources(
            actor.patient_id
        ):
            fresh.append({"id": str(source_id), "kind": name.lower(), "label": f"{name} due {due}"})
        if fresh != booking.choices["entries"]:
            _rotate(booking, now)
            _show_source(session, actor, booking, "Your booking options changed.")
            return True
    parsed, selected = parse_menu_command(command, booking.menu_token, booking.choices["count"])
    if parsed == "invalid":
        queue_reply(
            session,
            actor,
            "That choice is invalid. Reply to the latest message or send STAFF for help.",
        )
        return True
    if parsed == "more":
        next_cursor = booking.choices["next_cursor"]
        if next_cursor >= len(booking.choices["entries"]):
            queue_reply(session, actor, "There are no more choices. Reply BOOK or STAFF.")
        else:
            entries, title = booking.choices["entries"], booking.choices["title"]
            _rotate(booking, now)
            _show_options(session, actor, booking, entries, title, next_cursor)
        return True
    if parsed != "select" or selected is None:
        return False
    choice = booking.choices["entries"][booking.choices["cursor"] + selected]
    if booking.state == "source":
        booking.follow_up_id = UUID(choice["id"]) if choice.get("kind") == "follow-up" else None
        booking.recall_id = UUID(choice["id"]) if choice.get("kind") == "recall" else None
        _rotate(booking, now)
        _offer_types(session, actor, booking)
    elif booking.state == "type":
        if choice["id"] == "unsure":
            transition(session, actor.clinic_id, contact, actor, "needs_staff")
            queue_reply(session, actor, _HANDOFF)
        else:
            booking.appointment_type_id = UUID(choice["id"])
            booking.selected_date = None
            booking.clinician_user_id = None
            _rotate(booking, now)
            _offer_dates(session, actor, booking, now)
    elif booking.choices["title"] == "Choose a date":
        selected = choice["id"]
        booking.selected_date = None if selected == "earliest" else date.fromisoformat(selected)
        clinic = ClinicDayRepository(session, actor.clinic_id).get_clinic()
        if clinic is None:
            raise RuntimeError("clinic not found")
        today = now.astimezone(ZoneInfo(clinic.timezone)).date()
        if (
            booking.selected_date is not None
            and not today <= booking.selected_date <= today + timedelta(days=6)
        ):
            _rotate(booking, now)
            _offer_dates(session, actor, booking, now)
            return True
        _rotate(booking, now)
        _offer_clinicians(session, actor, booking)
    elif booking.choices["title"] == "Choose a clinician":
        if choice["id"] != "any" and choice not in _all_clinicians(session, actor):
            _rotate(booking, now)
            _offer_clinicians(session, actor, booking)
            return True
        booking.clinician_user_id = None if choice["id"] == "any" else UUID(choice["id"])
        _rotate(booking, now)
        _offer_slots(session, actor, booking, now, booking.selected_date, booking.clinician_user_id)
    else:
        booking.clinician_user_id = UUID(choice["id"])
        booking.state = "confirmation"
        booking.choices = {"selected": choice}
        _rotate(booking, now)
        type_name = next(
            (
                item["label"]
                for item in _all_types(session, actor)
                if item["id"] == str(booking.appointment_type_id)
            ),
            "Appointment",
        )
        queue_reply(
            session,
            actor,
            f"*Please check your appointment*\n\n{type_name}\n{choice['label']}\n\n"
            "Your appointment is not reserved yet.\n\n"
            "1\ufe0f\u20e3 Confirm booking\n2\ufe0f\u20e3 Change time\n"
            "3\ufe0f\u20e3 Change appointment type\n\n"
            "Use WhatsApp Reply on this message, then send your choice.",
            booking=booking,
            kind="menu",
        )
    return True


def _start(
    session: Session,
    actor: WhatsAppActor,
    contact: MessagingContact,
    now: datetime,
    previous: list[dict[str, str]] | None = None,
    notice: str = "",
) -> None:
    booking = _new_session(session, actor, contact, "visits", now)
    visits = _visit_snapshot(session, actor, now)
    display = list(visits)
    current_ids = {visit["id"] for visit in visits}
    for old in previous or []:
        if old["id"] in current_ids:
            continue
        detail = AppointmentRepository(session, actor.clinic_id).get_detail(UUID(old["id"]))
        if detail is None or detail[0].patient_id != actor.patient_id:
            continue
        visit, _, clinician, kind = detail
        display.append(
            {
                "id": str(visit.id),
                "starts_at": visit.starts_at.isoformat(),
                "ends_at": visit.ends_at.isoformat(),
                "status": visit.status,
                "clinician_id": str(visit.clinician_user_id),
                "type_id": str(visit.appointment_type_id),
                "clinician_name": clinician.full_name,
                "type_name": kind.name,
            }
        )
    if not display:
        _show_source(session, actor, booking, notice)
    else:
        booking.choices = {"visits": visits, "display": display, "cursor": 0}
        _show_visits(session, actor, booking, notice)


def _visit_command(
    session: Session,
    actor: WhatsAppActor,
    contact: MessagingContact,
    booking: WhatsAppBookingSession,
    command: str,
    now: datetime,
) -> bool:
    if not command.startswith(("MORE", "ANOTHER", "CONTINUE")):
        return False
    expected = booking.choices["visits"]
    if _visit_snapshot(session, actor, now) != expected:
        booking.state = "stopped"
        session.flush()
        _start(session, actor, contact, now, expected)
        return True
    token = booking.menu_token
    display = booking.choices["display"]
    if command == f"MORE {token}" and booking.choices["next_cursor"] < len(display):
        booking.choices = {
            "visits": expected,
            "display": display,
            "cursor": booking.choices["next_cursor"],
        }
        _rotate(booking, now)
        _show_visits(session, actor, booking)
    elif booking.choices["next_cursor"] == len(display) and (
        (command == f"ANOTHER {token}" and expected)
        or (command == f"CONTINUE {token}" and not expected)
    ):
        booking.acknowledged_visits = expected
        _rotate(booking, now)
        _show_source(session, actor, booking)
    else:
        queue_reply(
            session,
            actor,
            "That choice is not available. Reply BOOK to resume or STAFF for reception.",
        )
    return True


def _result_text(
    session: Session, actor: WhatsAppActor, booking: WhatsAppBookingSession, now: datetime
) -> str:
    if booking.booked_appointment_id is None:
        raise RuntimeError("booked visit is missing")
    detail = AppointmentRepository(session, actor.clinic_id).get_detail(
        booking.booked_appointment_id
    )
    clinic = ClinicDayRepository(session, actor.clinic_id).get_clinic()
    if detail is None or clinic is None or detail[0].patient_id != actor.patient_id:
        raise RuntimeError("booked visit is not available")
    visit, _, clinician, kind = detail
    local = visit.starts_at.astimezone(ZoneInfo(clinic.timezone))
    local_end = visit.ends_at.astimezone(ZoneInfo(clinic.timezone))
    return (
        f"*Appointment update*\n\n{local:%d %b %Y} at {local:%H:%M}–{local_end:%H:%M}\n"
        f"{kind.name} with {clinician.full_name}\nStatus: {visit.status}\n\n"
        f"Updated {now.astimezone(ZoneInfo(clinic.timezone)):%d %b %Y at %H:%M %Z}."
    )


def _confirm(
    session: Session,
    actor: WhatsAppActor,
    contact: MessagingContact,
    booking: WhatsAppBookingSession,
    now: datetime,
) -> None:
    from sqlalchemy.exc import IntegrityError

    from dentacircle.services.appointment_service import PatientBusyError, SlotTakenError
    from dentacircle.services.follow_up_service import (
        FollowUpInvalidStatusError,
        FollowUpNotFoundError,
    )
    from dentacircle.services.recall_service import RecallInvalidStatusError, RecallNotFoundError

    if booking.automation_version != contact.automation_version or booking.expires_at <= now:
        queue_reply(session, actor, "That confirmation expired. Reply START OVER or STAFF.")
        return
    if _visit_snapshot(session, actor, now) != booking.acknowledged_visits:
        booking.state = "stopped"
        session.flush()
        _start(
            session,
            actor,
            contact,
            now,
            booking.acknowledged_visits,
            "Your appointments changed. Please review them again.",
        )
        return
    choice = booking.choices["selected"]
    if booking.appointment_type_id is None or booking.clinician_user_id is None:
        raise RuntimeError("booking choice is missing")
    starts = datetime.fromisoformat(choice["start"])
    try:
        with session.begin_nested():
            available = find_availability(
                session,
                actor.clinic_id,
                booking.clinician_user_id,
                booking.appointment_type_id,
                starts.date(),
                now,
            )
            if not any(
                slot.starts_at == starts and slot.ends_at.isoformat() == choice["end"]
                for slot in available.slots
            ):
                raise SlotTakenError
            args = (session, actor.clinic_id, actor)
            if booking.follow_up_id is not None:
                visit = book_follow_up(
                    *args,
                    booking.follow_up_id,
                    booking.clinician_user_id,
                    booking.appointment_type_id,
                    starts,
                    now,
                )
            elif booking.recall_id is not None:
                visit = book_recall(
                    *args,
                    booking.recall_id,
                    booking.clinician_user_id,
                    booking.appointment_type_id,
                    starts,
                    now,
                )
            else:
                visit = book_appointment(
                    *args,
                    actor.patient_id,
                    booking.clinician_user_id,
                    booking.appointment_type_id,
                    starts,
                    now,
                )
    except (
        AppointmentFieldError,
        PatientBusyError,
        SlotTakenError,
        FollowUpInvalidStatusError,
        FollowUpNotFoundError,
        RecallInvalidStatusError,
        RecallNotFoundError,
        IntegrityError,
    ):
        booking.state = "stopped"
        session.flush()
        _start(
            session,
            actor,
            contact,
            now,
            booking.acknowledged_visits,
            "That time is no longer available. Please choose again or contact reception.",
        )
        return
    booking.booked_appointment_id = visit.id
    booking.state = "booked"
    session.flush()
    queue_reply(
        session, actor, _result_text(session, actor, booking, now), booking=booking, kind="result"
    )


class BookingResultUnavailable(Exception):
    """A committed result could not be refreshed and must stay queued."""


def render_queued_reply(session: Session, row: Message) -> str | None:
    """Recheck menu versions or refresh a committed result immediately before claim."""
    if row.booking_session_id is None and row.reply_kind != "menu":
        return row.body
    contact = session.scalar(
        select(MessagingContact)
        .where(
            MessagingContact.clinic_id == row.clinic_id,
            MessagingContact.id == row.contact_id,
            MessagingContact.account_key == row.account_key,
        )
        .with_for_update()
    )
    if row.booking_session_id is None:
        if (
            contact is None
            or contact.automation_state != "active"
            or contact.automation_version != row.automation_version
        ):
            return None
        return row.body
    booking = session.scalar(
        select(WhatsAppBookingSession)
        .where(
            WhatsAppBookingSession.clinic_id == row.clinic_id,
            WhatsAppBookingSession.id == row.booking_session_id,
            WhatsAppBookingSession.contact_id == row.contact_id,
            WhatsAppBookingSession.account_key == row.account_key,
        )
        .with_for_update()
    )
    if contact is None or booking is None:
        if row.reply_kind == "result":
            raise BookingResultUnavailable
        return None
    if row.reply_kind == "result":
        if row.caused_by_message_id is None:
            raise BookingResultUnavailable
        actor = WhatsAppActor(
            row.clinic_id, contact.patient_id, row.caused_by_message_id, row.account_key
        )
        try:
            return _result_text(session, actor, booking, datetime.now(UTC))
        except RuntimeError as exc:
            raise BookingResultUnavailable from exc
    if row.reply_kind == "control_ack":
        return row.body
    if (
        row.menu_version != booking.menu_version
        or row.automation_version != booking.automation_version
        or row.automation_version != contact.automation_version
        or booking.expires_at <= datetime.now(UTC)
    ):
        return None
    if row.reply_kind == "resume_challenge":
        return (
            row.body
            if contact.automation_state != "active" and booking.state == "resume_challenge"
            else None
        )
    return row.body if contact.automation_state == "active" and booking.state in _ACTIVE else None
