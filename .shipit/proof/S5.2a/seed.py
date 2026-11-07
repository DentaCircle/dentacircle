"""Seed a disposable database for S5.2a's synthetic proof."""
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from alembic import command
from sqlalchemy import select
from sqlalchemy.orm import Session
from dentacircle.core.config import Settings
from dentacircle.core.database import clear_engine, get_engine
from dentacircle.integrations.messaging.base import Connection, IncomingText
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.messaging import Message
from dentacircle.services.appointment_service import book_appointment
from dentacircle.services.automatic_dispatch import dispatch_one
from dentacircle.services.automatic_reply_service import queue_reply
from dentacircle.services.messaging_service import link_contact, receive_message
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from dentacircle.services.whatsapp_actor import authenticate_callback, resolve_actor
from tests.support import create_throwaway_database
from tests.test_migrations import _config

class UnknownProvider:
    def connection(self):
        return Connection("connected", True)
    def send_text(self, number, body):
        return "unknown"
    def normalize_event(self, payload):
        return None


def main():
    db = create_throwaway_database("postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle")
    Path('/private/tmp/s52a-proof-db').write_text(db)
    os.environ['DATABASE_URL'] = db
    command.upgrade(_config(), "head")
    clear_engine()
    number = '+15551234567'
    with Session(get_engine(), expire_on_commit=False) as session:
        clinic = get_or_create_clinic(session, 'Synthetic Demo Clinic')
        actor = create_user(session, clinic.id, 'proof@example.test', 'Synthetic Staff',
                            'synthetic-proof-password', ['clinic_admin', 'clinician', 'receptionist'])
        patient = register_patient(session, clinic.id, actor.id, 'Sample Patient', '9000000001', None)
        session.commit()
        contact = link_contact(session, clinic.id, actor.id, patient.id, 'demo', number, {number})
        settings = Settings(database_url=db, messaging_clinic_id=str(clinic.id),
                            messaging_callback_secret='synthetic-secret', messaging_account='demo',
                            messaging_allowlist=number, _env_file=None)
        authority = authenticate_callback('synthetic-secret', settings)
        receive_message(session, clinic.id, IncomingText('demo', number, 'proof-inbound-1', 'BOOK', None))
        incoming = session.scalar(select(Message).where(Message.provider_message_id == 'proof-inbound-1'))
        wa_actor = resolve_actor(session, authority, incoming.id)
        kind = session.scalar(select(AppointmentType).where(AppointmentType.clinic_id == clinic.id).limit(1))
        zone = ZoneInfo('Asia/Kolkata')
        now = datetime.now(UTC)
        day = now.astimezone(zone).date() + timedelta(days=1)
        while day.weekday() == 6:
            day += timedelta(days=1)
        start = datetime(day.year, day.month, day.day, 10, 0, tzinfo=zone)
        book_appointment(session, clinic.id, wa_actor, patient.id, actor.id, kind.id, start, now)
        queue_reply(session, wa_actor, 'Synthetic automatic reply: your request is being processed.')
        session.commit()
        clinic_id, contact_id, patient_id = clinic.id, contact.id, patient.id
    dispatch_one(get_engine(), UnknownProvider(), clinic_id, contact_id, 'demo', {number})
    with Session(get_engine(), expire_on_commit=False) as session:
        receive_message(session, clinic_id, IncomingText('demo', number, 'proof-inbound-2', 'STATUS', None))
        incoming = session.scalar(select(Message).where(Message.provider_message_id == 'proof-inbound-2'))
        authority = authenticate_callback('synthetic-secret', settings)
        wa_actor = resolve_actor(session, authority, incoming.id)
        queue_reply(session, wa_actor, 'Synthetic automatic reply queued for dispatch.')
        session.commit()
    Path('/private/tmp/s52a-proof-info.json').write_text(json.dumps({'patient_id': str(patient_id)}))
    print('Synthetic proof database seeded')

if __name__ == '__main__':
    main()
