"""Upload, list and read one clinic's patient documents.

The file is stored first, then the row and the audit event are committed together. If the
commit fails the stored file is deleted. This service owns that commit, because the route
cannot undo a file after the fact.
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from dentacircle.domain.document import check_upload, clean_filename
from dentacircle.integrations.storage import DocumentStorage, StorageNotFoundError
from dentacircle.models.document import Document
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.document_repository import DocumentRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.audit_service import record
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.patient_service import PatientNotFoundError

_logger = logging.getLogger("dentacircle.documents")


class DocumentNotFoundError(Exception):
    """No such document for this patient in the caller's clinic, or its file is missing."""


class DocumentPatientInactiveError(Exception):
    """An inactive patient cannot receive a new document."""


@dataclass(frozen=True)
class UploaderView:
    id: UUID
    name: str


@dataclass(frozen=True)
class DocumentView:
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    uploaded_by: UploaderView


@dataclass(frozen=True)
class DocumentPage:
    items: list[DocumentView]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class DocumentFile:
    view: DocumentView
    chunks: Iterator[bytes]


def require_patient(session: Session, clinic_id: UUID, patient_id: UUID) -> None:
    """404 when this clinic has no such patient. An inactive patient is fine."""
    if PatientRepository(session, clinic_id).get(patient_id) is None:
        raise PatientNotFoundError


def upload_document(
    session: Session,
    storage: DocumentStorage,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient_id: UUID,
    filename: str,
    declared_content_type: str | None,
    data: bytes,
) -> DocumentView:
    """Store the bytes, then commit the row and its audit event. Nothing is left on failure."""
    cleaned = clean_filename(filename)
    content_type = check_upload(data, declared_content_type)
    patient = PatientRepository(session, clinic_id).get(patient_id)
    if patient is None:
        raise PatientNotFoundError
    if patient.status != "active":
        raise DocumentPatientInactiveError
    document_id = uuid4()
    document = Document(
        id=document_id,
        patient_id=patient_id,
        uploaded_by_user_id=actor_user_id,
        filename=cleaned,
        content_type=content_type,
        size_bytes=len(data),
        storage_key=f"{clinic_id}/{document_id}",
    )
    storage.put(document.storage_key, data)
    try:
        view = _write_row(session, clinic_id, actor_user_id, document)
        session.commit()
    except BaseException:
        session.rollback()
        storage.delete(document.storage_key)
        raise
    return view


def list_documents(
    session: Session, clinic_id: UUID, patient_id: UUID, page: int, page_size: int
) -> DocumentPage:
    """This clinic's documents for the patient, newest first. An unknown patient is an error."""
    require_patient(session, clinic_id, patient_id)
    zone = _zone(session, clinic_id)
    repository = DocumentRepository(session, clinic_id)
    rows, total = repository.list_for_patient(patient_id, page, page_size)
    names = repository.uploader_names({row.uploaded_by_user_id for row in rows})
    return DocumentPage(
        items=[_view(row, zone, names) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def open_document(
    session: Session,
    storage: DocumentStorage,
    clinic_id: UUID,
    patient_id: UUID,
    document_id: UUID,
) -> DocumentFile:
    """The bytes of one document. The storage key comes from the row, never from the request."""
    repository = DocumentRepository(session, clinic_id)
    row = repository.get_for_patient(patient_id, document_id)
    if row is None:
        raise DocumentNotFoundError
    zone = _zone(session, clinic_id)
    names = repository.uploader_names({row.uploaded_by_user_id})
    view = _view(row, zone, names)
    try:
        chunks = storage.open(row.storage_key)
    except StorageNotFoundError:
        # The row says a file exists and storage disagrees. Log ids only, never the name.
        _logger.error("document file missing document_id=%s", document_id)
        raise DocumentNotFoundError from None
    return DocumentFile(view=view, chunks=chunks)


def _write_row(
    session: Session, clinic_id: UUID, actor_user_id: UUID, document: Document
) -> DocumentView:
    repository = DocumentRepository(session, clinic_id)
    repository.add(document)
    record(session, clinic_id, actor_user_id, "document", document.id, "create", changed_fields=[])
    session.flush()
    session.refresh(document)
    names = repository.uploader_names({actor_user_id})
    return _view(document, _zone(session, clinic_id), names)


def _view(row: Document, zone: ZoneInfo, names: dict[UUID, str]) -> DocumentView:
    name = names.get(row.uploaded_by_user_id)
    if name is None:
        raise RuntimeError("document points at a missing uploader")
    return DocumentView(
        id=row.id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        uploaded_at=row.created_at.astimezone(zone),
        uploaded_by=UploaderView(id=row.uploaded_by_user_id, name=name),
    )


def _zone(session: Session, clinic_id: UUID) -> ZoneInfo:
    clinic = ClinicDayRepository(session, clinic_id).get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    try:
        return ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        raise ClinicNotFoundError from None
