"""Upload, list and read one clinic's patient documents.

The file is stored first, then the row and the audit event are committed together. If the
commit fails the stored file is deleted. This service owns that commit, because the route
cannot undo a file after the fact.
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from dentacircle.domain.document import check_upload, clean_filename
from dentacircle.integrations.storage import DocumentStorage, StorageNotFoundError
from dentacircle.models.document import Document
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.document_repository import DocumentRepository
from dentacircle.repositories.follow_up_repository import FollowUpRepository
from dentacircle.repositories.lab_work_repository import LabWorkRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.audit_service import record
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.patient_service import PatientNotFoundError
from dentacircle.services.timeline_service import record as record_timeline

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
class AppointmentLinkView:
    id: UUID
    starts_at: datetime
    type_name: str


@dataclass(frozen=True)
class FollowUpLinkView:
    id: UUID
    due_on: date


@dataclass(frozen=True)
class LabWorkLinkView:
    id: UUID
    title: str
    status: str


@dataclass(frozen=True)
class DocumentView:
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    uploaded_by: UploaderView
    appointment: AppointmentLinkView | None
    follow_up: FollowUpLinkView | None
    lab_work: LabWorkLinkView | None


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
    *,
    appointment_id: UUID | None = None,
    follow_up_id: UUID | None = None,
    lab_work_id: UUID | None = None,
) -> DocumentView:
    """Store the bytes, then commit the row, its audit event and timeline step together."""
    cleaned = clean_filename(filename)
    content_type = check_upload(data, declared_content_type)
    patient = PatientRepository(session, clinic_id).get(patient_id)
    if patient is None:
        raise PatientNotFoundError
    _require_owned_links(
        session, clinic_id, patient_id, appointment_id, follow_up_id, lab_work_id
    )
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
        appointment_id=appointment_id,
        follow_up_id=follow_up_id,
        lab_work_id=lab_work_id,
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
    session: Session,
    clinic_id: UUID,
    patient_id: UUID,
    page: int,
    page_size: int,
    *,
    appointment_id: UUID | None = None,
    follow_up_id: UUID | None = None,
    lab_work_id: UUID | None = None,
) -> DocumentPage:
    """This clinic's documents for the patient, newest first. An unknown patient is an error.

    A filter id from another patient or clinic matches nothing and is an empty page, not an error.
    """
    require_patient(session, clinic_id, patient_id)
    repository = DocumentRepository(session, clinic_id)
    rows, total = repository.list_for_patient(
        patient_id,
        page,
        page_size,
        appointment_id=appointment_id,
        follow_up_id=follow_up_id,
        lab_work_id=lab_work_id,
    )
    return DocumentPage(
        items=_views(session, clinic_id, rows),
        total=total,
        page=page,
        page_size=page_size,
    )


def get_document(
    session: Session, clinic_id: UUID, patient_id: UUID, document_id: UUID
) -> DocumentView:
    """One document for this patient. An inactive patient stays readable."""
    repository = DocumentRepository(session, clinic_id)
    row = repository.get_for_patient(patient_id, document_id)
    if row is None:
        raise DocumentNotFoundError
    return _views(session, clinic_id, [row])[0]


def update_document_links(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient_id: UUID,
    document_id: UUID,
    *,
    set_appointment: bool,
    appointment_id: UUID | None,
    set_follow_up: bool,
    follow_up_id: UUID | None,
    set_lab_work: bool = False,
    lab_work_id: UUID | None = None,
) -> DocumentView:
    """Set or clear links. An omitted side is left as it is. A no-op writes no audit event."""
    patient = PatientRepository(session, clinic_id).get(patient_id)
    if patient is None:
        raise PatientNotFoundError
    repository = DocumentRepository(session, clinic_id)
    row = repository.get_for_patient(patient_id, document_id)
    if row is None:
        raise DocumentNotFoundError
    next_appointment = appointment_id if set_appointment else row.appointment_id
    next_follow_up = follow_up_id if set_follow_up else row.follow_up_id
    next_lab_work = lab_work_id if set_lab_work else row.lab_work_id
    _require_owned_links(
        session, clinic_id, patient_id, next_appointment, next_follow_up, next_lab_work
    )
    if patient.status != "active":
        raise DocumentPatientInactiveError
    changed: list[str] = []
    if set_appointment and row.appointment_id != appointment_id:
        row.appointment_id = appointment_id
        changed.append("appointment_id")
    if set_follow_up and row.follow_up_id != follow_up_id:
        row.follow_up_id = follow_up_id
        changed.append("follow_up_id")
    if set_lab_work and row.lab_work_id != lab_work_id:
        row.lab_work_id = lab_work_id
        changed.append("lab_work_id")
    if changed:
        record(
            session,
            clinic_id,
            actor_user_id,
            "document",
            row.id,
            "update",
            changed_fields=changed,
        )
        session.commit()
    return _views(session, clinic_id, [row])[0]


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
    view = _views(session, clinic_id, [row])[0]
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
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        document.patient_id,
        "document_uploaded",
        document_id=document.id,
    )
    session.flush()
    session.refresh(document)
    return _views(session, clinic_id, [document])[0]


def _require_owned_links(
    session: Session,
    clinic_id: UUID,
    patient_id: UUID,
    appointment_id: UUID | None,
    follow_up_id: UUID | None,
    lab_work_id: UUID | None,
) -> None:
    """Each link, when set, belongs to this patient in this clinic. Otherwise 404."""
    if appointment_id is not None:
        visit = AppointmentRepository(session, clinic_id).get_for_patient(
            appointment_id, patient_id
        )
        if visit is None:
            raise DocumentNotFoundError
    if follow_up_id is not None:
        follow_up = FollowUpRepository(session, clinic_id).get_for_patient(follow_up_id, patient_id)
        if follow_up is None:
            raise DocumentNotFoundError
    if lab_work_id is not None:
        lab_work = LabWorkRepository(session, clinic_id).get_for_patient(lab_work_id, patient_id)
        if lab_work is None:
            raise DocumentNotFoundError


def _views(session: Session, clinic_id: UUID, rows: list[Document]) -> list[DocumentView]:
    zone = _zone(session, clinic_id)
    repository = DocumentRepository(session, clinic_id)
    names = repository.uploader_names({row.uploaded_by_user_id for row in rows})
    appointments = repository.appointment_links(
        {row.appointment_id for row in rows if row.appointment_id is not None}
    )
    follow_ups = repository.follow_up_links(
        {row.follow_up_id for row in rows if row.follow_up_id is not None}
    )
    lab_work = repository.lab_work_links(
        {row.lab_work_id for row in rows if row.lab_work_id is not None}
    )
    return [_view(row, zone, names, appointments, follow_ups, lab_work) for row in rows]


def _view(
    row: Document,
    zone: ZoneInfo,
    names: dict[UUID, str],
    appointments: dict[UUID, tuple[datetime, str]],
    follow_ups: dict[UUID, date],
    lab_work: dict[UUID, tuple[str, str]],
) -> DocumentView:
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
        appointment=_appointment_link(row, zone, appointments),
        follow_up=_follow_up_link(row, follow_ups),
        lab_work=_lab_work_link(row, lab_work),
    )


def _appointment_link(
    row: Document, zone: ZoneInfo, appointments: dict[UUID, tuple[datetime, str]]
) -> AppointmentLinkView | None:
    if row.appointment_id is None:
        return None
    found = appointments.get(row.appointment_id)
    if found is None:
        raise RuntimeError("document points at a missing visit")
    starts_at, type_name = found
    return AppointmentLinkView(
        id=row.appointment_id,
        starts_at=starts_at.astimezone(zone),
        type_name=type_name,
    )


def _lab_work_link(
    row: Document, lab_work: dict[UUID, tuple[str, str]]
) -> LabWorkLinkView | None:
    if row.lab_work_id is None:
        return None
    found = lab_work.get(row.lab_work_id)
    if found is None:
        raise RuntimeError("document points at missing lab work")
    title, status = found
    return LabWorkLinkView(id=row.lab_work_id, title=title, status=status)


def _follow_up_link(row: Document, follow_ups: dict[UUID, date]) -> FollowUpLinkView | None:
    if row.follow_up_id is None:
        return None
    due_on = follow_ups.get(row.follow_up_id)
    if due_on is None:
        raise RuntimeError("document points at a missing follow-up")
    return FollowUpLinkView(id=row.follow_up_id, due_on=due_on)


def _zone(session: Session, clinic_id: UUID) -> ZoneInfo:
    clinic = ClinicDayRepository(session, clinic_id).get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    try:
        return ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        raise ClinicNotFoundError from None
