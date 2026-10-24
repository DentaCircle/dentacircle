"""Upload, list, view and link a patient's documents."""

from datetime import date, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, model_validator

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.document import (
    DOCUMENT_CONTENT_TYPES,
    DOCUMENT_FILENAME_HEADER,
    DOCUMENT_READ_ROLES,
    DOCUMENT_WRITE_ROLES,
    IMAGE_INLINE_CSP,
    MAX_DOCUMENT_BYTES,
    DocumentFieldError,
    UnsupportedMediaTypeError,
    clean_filename,
    content_disposition,
    decode_filename_header,
    is_inline_image,
)
from dentacircle.integrations.storage import DocumentStorage, get_storage
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.document_service import (
    AppointmentLinkView,
    DocumentNotFoundError,
    DocumentPatientInactiveError,
    DocumentView,
    FollowUpLinkView,
    LabWorkLinkView,
    get_document,
    list_documents,
    open_document,
    require_patient,
    update_document_links,
    upload_document,
)
from dentacircle.services.patient_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PatientNotFoundError,
)

router = APIRouter()

can_read = require_roles(*DOCUMENT_READ_ROLES)
can_write = require_roles(*DOCUMENT_WRITE_ROLES)

StorageDep = Annotated[DocumentStorage, Depends(get_storage)]

DocumentContentType = Literal["application/pdf", "image/png", "image/jpeg"]

MAX_PAGE = (2**63 - 1) // MAX_PAGE_SIZE + 1


class UploaderBody(BaseModel):
    id: UUID
    name: str


class AppointmentLinkBody(BaseModel):
    id: UUID
    starts_at: datetime
    type_name: str


class FollowUpLinkBody(BaseModel):
    id: UUID
    due_on: date


class LabWorkLinkBody(BaseModel):
    id: UUID
    title: str
    status: str


class DocumentBody(BaseModel):
    id: UUID
    filename: str
    content_type: DocumentContentType
    size_bytes: int
    uploaded_at: datetime
    uploaded_by: UploaderBody
    appointment: AppointmentLinkBody | None
    follow_up: FollowUpLinkBody | None
    lab_work: LabWorkLinkBody | None


class DocumentLinksUpdate(BaseModel):
    """A present field is set (UUID) or cleared (null). An omitted field stays as it is."""

    model_config = ConfigDict(extra="forbid")

    appointment_id: UUID | None = None
    follow_up_id: UUID | None = None
    lab_work_id: UUID | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "DocumentLinksUpdate":
        if not self.model_fields_set:
            raise ValueError("empty")
        return self


class DocumentListResponse(BaseModel):
    items: list[DocumentBody]
    total: int
    page: int
    page_size: int


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
}
_LIST_ERRORS: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_UPLOAD_ERRORS: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    409: {"model": ErrorResponse, "description": "patient_inactive"},
    413: {"model": ErrorResponse, "description": "payload_too_large"},
    415: {"model": ErrorResponse, "description": "unsupported_media_type"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_LINK_ERRORS: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    409: {"model": ErrorResponse, "description": "patient_inactive"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_BINARY = {"schema": {"type": "string", "format": "binary"}}
_UPLOAD_OPENAPI: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/pdf": _BINARY,
            "image/png": _BINARY,
            "image/jpeg": _BINARY,
        },
    }
}
_DOWNLOAD_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    200: {
        "description": "The file bytes. disposition=inline or attachment (the default).",
        "content": {"application/pdf": {}, "image/png": {}, "image/jpeg": {}},
    },
}


@router.post(
    "/patients/{patient_id}/documents",
    status_code=201,
    responses=_UPLOAD_ERRORS,
    openapi_extra=_UPLOAD_OPENAPI,
)
async def post_document(
    request: Request,
    patient_id: UUID,
    filename: Annotated[str, Header(alias=DOCUMENT_FILENAME_HEADER)],
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
    storage: StorageDep,
    appointment_id: Annotated[UUID | None, Query()] = None,
    follow_up_id: Annotated[UUID | None, Query()] = None,
    lab_work_id: Annotated[UUID | None, Query()] = None,
) -> DocumentBody:
    """The raw file is the request body. The name is in a header so access logs stay clean."""
    try:
        clean_filename(decode_filename_header(filename))
    except DocumentFieldError as exc:
        raise _field_error(exc) from None
    try:
        await run_in_threadpool(require_patient, session, user.clinic.id, patient_id)
    except PatientNotFoundError:
        raise HTTPException(status_code=404) from None
    await run_in_threadpool(session.rollback)
    data = await _read_body(request)
    try:
        created = await run_in_threadpool(
            upload_document,
            session,
            storage,
            user.clinic.id,
            user.id,
            patient_id,
            decode_filename_header(filename),
            request.headers.get("content-type"),
            data,
            appointment_id=appointment_id,
            follow_up_id=follow_up_id,
            lab_work_id=lab_work_id,
        )
    except DocumentFieldError as exc:
        raise _field_error(exc) from None
    except UnsupportedMediaTypeError:
        raise CodedHttpError(
            415, "unsupported_media_type", "That file type is not allowed."
        ) from None
    except (PatientNotFoundError, DocumentNotFoundError):
        raise HTTPException(status_code=404) from None
    except DocumentPatientInactiveError:
        raise CodedHttpError(409, "patient_inactive", "This patient is inactive.") from None
    return _document(created)


@router.get("/patients/{patient_id}/documents", responses=_LIST_ERRORS)
def get_documents(
    patient_id: UUID,
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    appointment_id: Annotated[UUID | None, Query()] = None,
    follow_up_id: Annotated[UUID | None, Query()] = None,
    lab_work_id: Annotated[UUID | None, Query()] = None,
) -> DocumentListResponse:
    try:
        found = list_documents(
            session,
            user.clinic.id,
            patient_id,
            page,
            page_size,
            appointment_id=appointment_id,
            follow_up_id=follow_up_id,
            lab_work_id=lab_work_id,
        )
    except (PatientNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    return DocumentListResponse(
        items=[_document(row) for row in found.items],
        total=found.total,
        page=found.page,
        page_size=found.page_size,
    )


@router.get("/patients/{patient_id}/documents/{document_id}", responses=_NOT_FOUND)
def get_one_document(
    patient_id: UUID,
    document_id: UUID,
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
) -> DocumentBody:
    try:
        found = get_document(session, user.clinic.id, patient_id, document_id)
    except (DocumentNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    return _document(found)


@router.patch(
    "/patients/{patient_id}/documents/{document_id}",
    responses=_LINK_ERRORS,
)
def patch_document_links(
    patient_id: UUID,
    document_id: UUID,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
    body: DocumentLinksUpdate,
) -> DocumentBody:
    try:
        updated = update_document_links(
            session,
            user.clinic.id,
            user.id,
            patient_id,
            document_id,
            set_appointment="appointment_id" in body.model_fields_set,
            appointment_id=body.appointment_id,
            set_follow_up="follow_up_id" in body.model_fields_set,
            follow_up_id=body.follow_up_id,
            set_lab_work="lab_work_id" in body.model_fields_set,
            lab_work_id=body.lab_work_id,
        )
    except (DocumentNotFoundError, PatientNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    except DocumentPatientInactiveError:
        raise CodedHttpError(409, "patient_inactive", "This patient is inactive.") from None
    return _document(updated)


@router.get("/patients/{patient_id}/documents/{document_id}/file", responses=_DOWNLOAD_RESPONSES)
def get_document_file(
    patient_id: UUID,
    document_id: UUID,
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
    storage: StorageDep,
    disposition: Annotated[Literal["inline", "attachment"], Query()] = "attachment",
) -> StreamingResponse:
    try:
        found = open_document(session, storage, user.clinic.id, patient_id, document_id)
    except (DocumentNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    headers = {
        "Content-Disposition": content_disposition(disposition, found.view.filename),
        "Content-Length": str(found.view.size_bytes),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }
    if disposition == "inline" and is_inline_image(found.view.content_type):
        headers["Content-Security-Policy"] = IMAGE_INLINE_CSP
    return StreamingResponse(found.chunks, media_type=found.view.content_type, headers=headers)


async def _read_body(request: Request) -> bytes:
    """The body, counted as it arrives. Stops at the first chunk past the limit."""
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > MAX_DOCUMENT_BYTES:
            raise CodedHttpError(413, "payload_too_large", "That file is too large.")
    return bytes(received)


def _field_error(exc: DocumentFieldError) -> RequestValidationError:
    location: tuple[str, ...]
    if exc.location == "filename":
        location = ("header", DOCUMENT_FILENAME_HEADER.lower())
    elif exc.location == "body":
        location = ("body",)
    else:
        location = (exc.location,)
    return RequestValidationError(
        [{"type": exc.code, "loc": location, "msg": exc.code, "input": None}]
    )


def _document(row: DocumentView) -> DocumentBody:
    return DocumentBody(
        id=row.id,
        filename=row.filename,
        content_type=_content_type(row.content_type),
        size_bytes=row.size_bytes,
        uploaded_at=row.uploaded_at,
        uploaded_by=UploaderBody(id=row.uploaded_by.id, name=row.uploaded_by.name),
        appointment=_appointment_link(row.appointment),
        follow_up=_follow_up_link(row.follow_up),
        lab_work=_lab_work_link(row.lab_work),
    )


def _appointment_link(link: AppointmentLinkView | None) -> AppointmentLinkBody | None:
    if link is None:
        return None
    return AppointmentLinkBody(id=link.id, starts_at=link.starts_at, type_name=link.type_name)


def _lab_work_link(link: LabWorkLinkView | None) -> LabWorkLinkBody | None:
    if link is None:
        return None
    return LabWorkLinkBody(id=link.id, title=link.title, status=link.status)


def _follow_up_link(link: FollowUpLinkView | None) -> FollowUpLinkBody | None:
    if link is None:
        return None
    return FollowUpLinkBody(id=link.id, due_on=link.due_on)


def _content_type(value: str) -> DocumentContentType:
    if value not in DOCUMENT_CONTENT_TYPES:
        raise RuntimeError("document has an unknown content type")
    return cast(DocumentContentType, value)
