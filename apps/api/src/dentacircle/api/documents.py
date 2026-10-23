"""Upload, list and download a patient's documents."""

from datetime import datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.document import (
    DOCUMENT_CONTENT_TYPES,
    DOCUMENT_FILENAME_HEADER,
    DOCUMENT_READ_ROLES,
    DOCUMENT_WRITE_ROLES,
    MAX_DOCUMENT_BYTES,
    DocumentFieldError,
    UnsupportedMediaTypeError,
    attachment_disposition,
    clean_filename,
    decode_filename_header,
)
from dentacircle.integrations.storage import DocumentStorage, get_storage
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.document_service import (
    DocumentNotFoundError,
    DocumentPatientInactiveError,
    DocumentView,
    list_documents,
    open_document,
    require_patient,
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


class DocumentBody(BaseModel):
    id: UUID
    filename: str
    content_type: DocumentContentType
    size_bytes: int
    uploaded_at: datetime
    uploaded_by: UploaderBody


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
        "description": "The file bytes, as an attachment.",
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
        )
    except DocumentFieldError as exc:
        raise _field_error(exc) from None
    except UnsupportedMediaTypeError:
        raise CodedHttpError(
            415, "unsupported_media_type", "That file type is not allowed."
        ) from None
    except PatientNotFoundError:
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
) -> DocumentListResponse:
    try:
        found = list_documents(session, user.clinic.id, patient_id, page, page_size)
    except (PatientNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    return DocumentListResponse(
        items=[_document(row) for row in found.items],
        total=found.total,
        page=found.page,
        page_size=found.page_size,
    )


@router.get("/patients/{patient_id}/documents/{document_id}/file", responses=_DOWNLOAD_RESPONSES)
def get_document_file(
    patient_id: UUID,
    document_id: UUID,
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
    storage: StorageDep,
) -> StreamingResponse:
    try:
        found = open_document(session, storage, user.clinic.id, patient_id, document_id)
    except (DocumentNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    return StreamingResponse(
        found.chunks,
        media_type=found.view.content_type,
        headers={
            "Content-Disposition": attachment_disposition(found.view.filename),
            "Content-Length": str(found.view.size_bytes),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


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
    )


def _content_type(value: str) -> DocumentContentType:
    if value not in DOCUMENT_CONTENT_TYPES:
        raise RuntimeError("document has an unknown content type")
    return cast(DocumentContentType, value)
