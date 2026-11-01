"""Staff messaging routes and the credential-protected OpenWA callback."""

import hmac
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.config import Settings, get_settings
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.patient import display_id
from dentacircle.integrations.messaging.openwa import OpenWaMessagingProvider
from dentacircle.models.messaging import Message
from dentacircle.repositories.messaging_repository import MessagingRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.messaging_service import (
    ContactConflict,
    MessagingInvalid,
    MessagingUnavailable,
    link_contact,
    receive_message,
    send_message,
)
from dentacircle.services.patient_service import PatientNotFoundError

router = APIRouter()
roles = require_roles("receptionist", "clinician", "clinic_admin")
UserDep = Annotated[CurrentUser, Depends(roles)]


class ContactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: str


class SendInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str
    request_id: UUID


class ContactBody(BaseModel):
    id: UUID
    patient_id: UUID
    number: str


class ActorBody(BaseModel):
    id: UUID
    name: str


class MessageBody(BaseModel):
    id: UUID
    patient_id: UUID
    direction: Literal["inbound", "outbound"]
    body: str
    state: Literal["received", "sending", "accepted", "failed", "unknown"]
    created_at: datetime
    updated_at: datetime
    provider_sent_at: datetime | None
    created_by: ActorBody | None


class PatientBody(BaseModel):
    id: UUID
    display_id: str
    full_name: str
    status: str


class InboxRow(BaseModel):
    patient: PatientBody
    latest_message: MessageBody
    message_count: int


class InboxPage(BaseModel):
    items: list[InboxRow]
    total: int
    page: int
    page_size: int


class HistoryPage(BaseModel):
    items: list[MessageBody]
    total: int
    page: int
    page_size: int


class ConnectionBody(BaseModel):
    status: Literal["connected", "disconnected", "unconfigured"]
    can_send_text: bool


def allowlist(settings: Settings) -> set[str]:
    return {number.strip() for number in settings.messaging_allowlist.split(",") if number.strip()}


def provider(settings: Settings) -> OpenWaMessagingProvider:
    return OpenWaMessagingProvider(
        settings.messaging_url, settings.messaging_api_key, settings.messaging_account
    )


def configured(settings: Settings, clinic_id: UUID) -> bool:
    return bool(
        settings.messaging_clinic_id
        and settings.messaging_clinic_id == str(clinic_id)
        and settings.messaging_account
        and settings.messaging_callback_secret
    )


def message_body(row: Message, patient_id: UUID, repository: MessagingRepository) -> MessageBody:
    actor = repository.actor(row.created_by_user_id) if row.created_by_user_id else None
    return MessageBody(
        id=row.id,
        patient_id=patient_id,
        direction=row.direction,
        body=row.body,
        state=row.state,
        created_at=row.created_at,
        updated_at=row.updated_at,
        provider_sent_at=row.provider_sent_at,
        created_by=ActorBody(id=actor.id, name=actor.full_name) if actor else None,
    )


def require_patient(session: SessionDep, clinic_id: UUID, patient_id: UUID) -> None:
    if PatientRepository(session, clinic_id).get(patient_id) is None:
        raise HTTPException(404)


def fail(exc: Exception) -> None:
    if isinstance(exc, PatientNotFoundError):
        raise HTTPException(404) from None
    if isinstance(exc, MessagingInvalid):
        raise CodedHttpError(422, "validation_error", "Invalid messaging input.") from None
    if isinstance(exc, MessagingUnavailable):
        raise CodedHttpError(503, "messaging_unavailable", "Messaging is unavailable.") from None
    raise CodedHttpError(
        409, "messaging_conflict", "This messaging action is not available."
    ) from None


@router.get("/messaging/connection")
def connection(user: UserDep) -> ConnectionBody:
    settings = get_settings()
    result = provider(settings).connection() if configured(settings, user.clinic.id) else None
    return ConnectionBody(
        status=result.status if result else "unconfigured",
        can_send_text=result.can_send_text if result else False,
    )


@router.get("/messages")
def inbox(
    user: UserDep,
    session: SessionDep,
    page: Annotated[int, Query(ge=1, le=92233720368547758)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> InboxPage:
    repo = MessagingRepository(session, user.clinic.id)
    rows, total = repo.inbox(page, page_size)
    return InboxPage(
        items=[
            InboxRow(
                patient=PatientBody(
                    id=p.id,
                    display_id=display_id(p.patient_number),
                    full_name=p.full_name,
                    status=p.status,
                ),
                latest_message=message_body(m, p.id, repo),
                message_count=n,
            )
            for p, m, n in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/patients/{patient_id}/messaging-contact")
def get_contact(patient_id: UUID, user: UserDep, session: SessionDep) -> ContactBody | None:
    require_patient(session, user.clinic.id, patient_id)
    row = MessagingRepository(session, user.clinic.id).contact_for_patient(patient_id)
    return ContactBody(id=row.id, patient_id=row.patient_id, number=row.number) if row else None


@router.put("/patients/{patient_id}/messaging-contact")
def put_contact(
    patient_id: UUID, body: ContactInput, user: UserDep, session: SessionDep
) -> ContactBody:
    require_patient(session, user.clinic.id, patient_id)
    settings = get_settings()
    if not configured(settings, user.clinic.id):
        raise CodedHttpError(503, "messaging_unavailable", "Messaging is unavailable.")
    try:
        row = link_contact(
            session,
            user.clinic.id,
            user.id,
            patient_id,
            settings.messaging_account,
            body.number,
            allowlist(settings),
        )
    except (PatientNotFoundError, MessagingInvalid, ContactConflict) as exc:
        fail(exc)
        raise AssertionError from exc
    return ContactBody(id=row.id, patient_id=row.patient_id, number=row.number)


@router.get("/patients/{patient_id}/messages")
def history(
    patient_id: UUID,
    user: UserDep,
    session: SessionDep,
    page: Annotated[int, Query(ge=1, le=92233720368547758)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HistoryPage:
    require_patient(session, user.clinic.id, patient_id)
    repo = MessagingRepository(session, user.clinic.id)
    contact = repo.contact_for_patient(patient_id)
    rows, total = repo.history(contact.id, page, page_size) if contact else ([], 0)
    return HistoryPage(
        items=[message_body(row, patient_id, repo) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/patients/{patient_id}/messages", status_code=201)
def send(
    patient_id: UUID, body: SendInput, response: Response, user: UserDep, session: SessionDep
) -> MessageBody:
    require_patient(session, user.clinic.id, patient_id)
    settings = get_settings()
    active_provider = (
        provider(settings)
        if configured(settings, user.clinic.id)
        else OpenWaMessagingProvider("", "", "")
    )
    try:
        row, created = send_message(
            session,
            active_provider,
            user.clinic.id,
            user.id,
            patient_id,
            body.body,
            body.request_id,
            settings.messaging_account,
            allowlist(settings),
        )
    except (PatientNotFoundError, MessagingInvalid, MessagingUnavailable, ContactConflict) as exc:
        fail(exc)
        raise AssertionError from exc
    response.status_code = 201 if created else 200
    return message_body(row, patient_id, MessagingRepository(session, user.clinic.id))


def callback_credential(
    secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
) -> None:
    expected = get_settings().messaging_callback_secret
    if not expected or not secret or not hmac.compare_digest(secret.encode(), expected.encode()):
        raise HTTPException(401)


callback_credential.credential_protected = True  # type: ignore[attr-defined]


@router.post("/integrations/messaging/openwa/events", status_code=204)
async def callback(
    request: Request,
    session: SessionDep,
    _: Annotated[None, Depends(callback_credential)],
) -> Response:
    settings = get_settings()
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Malformed event")
        clinic_id = UUID(settings.messaging_clinic_id)
        event = provider(settings).normalize_event(payload)
        if event is not None and event.number in allowlist(settings):
            await run_in_threadpool(receive_message, session, clinic_id, event)
    except ValueError:
        raise HTTPException(422) from None
    except SQLAlchemyError:
        await run_in_threadpool(session.rollback)
        raise CodedHttpError(503, "messaging_unavailable", "Messaging is unavailable.") from None
    return Response(status_code=204)
