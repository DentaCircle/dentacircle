"""Resolve a WhatsApp initiator only from a persisted, linked inbound message."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from dentacircle.core.config import Settings
from dentacircle.repositories.messaging_repository import MessagingRepository

_SIGNING_KEY = secrets.token_bytes(32)


class InvalidCallbackCredential(Exception):
    """The callback credential was not accepted."""


@dataclass(frozen=True)
class VerifiedCallback:
    clinic_id: UUID
    account_key: str
    allowlist: frozenset[str]
    _seal: bytes = field(default=b"", repr=False)


def _sign(*parts: str) -> bytes:
    return hmac.new(_SIGNING_KEY, "\0".join(parts).encode(), hashlib.sha256).digest()


def authenticate_callback(secret: str | None, settings: Settings) -> VerifiedCallback:
    expected = settings.messaging_callback_secret
    if not expected or not secret or not hmac.compare_digest(secret.encode(), expected.encode()):
        raise InvalidCallbackCredential
    clinic_id = UUID(settings.messaging_clinic_id)
    allowlist = frozenset(
        number.strip() for number in settings.messaging_allowlist.split(",") if number.strip()
    )
    account = settings.messaging_account
    seal = _sign("callback", str(clinic_id), account, *sorted(allowlist))
    return VerifiedCallback(clinic_id, account, allowlist, seal)


class InvalidWhatsAppActor(Exception):
    """The message cannot act for this patient and clinic."""


@dataclass(frozen=True)
class WhatsAppActor:
    clinic_id: UUID
    patient_id: UUID
    message_id: UUID
    account_key: str
    _seal: bytes = field(default=b"", repr=False)


def resolve_actor(session: Session, callback: VerifiedCallback, message_id: UUID) -> WhatsAppActor:
    expected = _sign(
        "callback", str(callback.clinic_id), callback.account_key, *sorted(callback.allowlist)
    )
    if not hmac.compare_digest(callback._seal, expected):
        raise InvalidWhatsAppActor
    clinic_id, account_key, allowlist = callback.clinic_id, callback.account_key, callback.allowlist
    result = MessagingRepository(session, clinic_id).inbound_identity(message_id, account_key)
    if result is None:
        raise InvalidWhatsAppActor
    message, contact, patient = result
    if contact.number not in allowlist:
        raise InvalidWhatsAppActor
    seal = _sign("actor", str(clinic_id), str(patient.id), str(message.id), account_key)
    return WhatsAppActor(clinic_id, patient.id, message.id, account_key, seal)


def require_patient(
    session: Session, actor: UUID | WhatsAppActor, clinic_id: UUID, patient_id: UUID
) -> None:
    if not isinstance(actor, WhatsAppActor):
        return
    expected = _sign(
        "actor",
        str(actor.clinic_id),
        str(actor.patient_id),
        str(actor.message_id),
        actor.account_key,
    )
    if not hmac.compare_digest(actor._seal, expected):
        raise InvalidWhatsAppActor
    if actor.clinic_id != clinic_id or actor.patient_id != patient_id:
        raise InvalidWhatsAppActor
    linked = MessagingRepository(session, clinic_id).inbound_identity(
        actor.message_id, actor.account_key
    )
    if linked is None or linked[2].id != patient_id:
        raise InvalidWhatsAppActor
