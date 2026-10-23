"""Document service: store, write order and rollback, inactive patients, audit, tenancy, read."""

import logging
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.document import DocumentFieldError, UnsupportedMediaTypeError
from dentacircle.integrations.storage.memory import MemoryStorage
from dentacircle.models.app_user import AppUser
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.document import Document
from dentacircle.models.patient import Patient
from dentacircle.services.document_service import (
    DocumentNotFoundError,
    DocumentPatientInactiveError,
    DocumentView,
    list_documents,
    open_document,
    upload_document,
)
from dentacircle.services.patient_service import PatientNotFoundError
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.timeline_support import World, world

pytest_plugins = ["tests.timeline_support"]

_PDF = b"%PDF-1.7\nsynthetic body"
_PNG = b"\x89PNG\r\n\x1a\nsynthetic body"
_NAME = "Synthetic Report.pdf"


def _upload(
    clinic: World,
    storage: MemoryStorage,
    *,
    filename: str = _NAME,
    content_type: str | None = "application/pdf",
    data: bytes = _PDF,
    patient_id: UUID | None = None,
    clinic_id: UUID | None = None,
    actor_id: UUID | None = None,
) -> DocumentView:
    with Session(get_engine()) as session:
        return upload_document(
            session,
            storage,
            clinic.clinic_id if clinic_id is None else clinic_id,
            clinic.actor_id if actor_id is None else actor_id,
            clinic.patient_id if patient_id is None else patient_id,
            filename,
            content_type,
            data,
        )


def _count(model: type[Document] | type[AuditEvent]) -> int:
    with Session(get_engine()) as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _document_audits() -> list[AuditEvent]:
    with Session(get_engine()) as session:
        return list(session.scalars(select(AuditEvent).where(AuditEvent.entity_type == "document")))


def _set_patient_status(patient_id: UUID, status: str) -> None:
    with Session(get_engine()) as session:
        patient = session.get(Patient, patient_id)
        assert patient is not None
        patient.status = status
        session.commit()


def _other_clinic() -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        other = get_or_create_clinic(session, "Another Synthetic Clinic")
        user = create_user(
            session,
            other.id,
            "other@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        session.commit()
        return other.id, user.id


def test_an_upload_stores_the_bytes_the_row_and_one_audit_event(database: str) -> None:
    clinic = world()
    storage = MemoryStorage()
    view = _upload(clinic, storage)
    assert view.filename == _NAME
    assert view.content_type == "application/pdf"
    assert view.size_bytes == len(_PDF)
    assert view.uploaded_by.id == clinic.actor_id
    assert view.uploaded_by.name == "Sample Desk"
    assert list(storage.files) == [f"{clinic.clinic_id}/{view.id}"]
    assert storage.files[f"{clinic.clinic_id}/{view.id}"] == _PDF
    with Session(get_engine()) as session:
        row = session.get(Document, view.id)
        assert row is not None
        assert row.storage_key == f"{clinic.clinic_id}/{view.id}"
        assert row.clinic_id == clinic.clinic_id
        assert row.patient_id == clinic.patient_id
    events = _document_audits()
    assert len(events) == 1
    assert events[0].action == "create"
    assert events[0].entity_id == view.id
    assert events[0].actor_user_id == clinic.actor_id
    assert events[0].clinic_id == clinic.clinic_id
    assert events[0].changed_fields == []


def test_the_stored_time_is_clinic_local(database: str) -> None:
    clinic = world()
    view = _upload(clinic, MemoryStorage())
    assert view.uploaded_at.utcoffset() is not None
    assert view.uploaded_at.utcoffset().total_seconds() == 5.5 * 3600  # type: ignore[union-attr]


def test_the_name_is_cleaned_before_it_is_stored(database: str) -> None:
    clinic = world()
    view = _upload(clinic, MemoryStorage(), filename="C:\\scans\\re\x00port.pdf")
    assert view.filename == "report.pdf"


def test_the_name_never_reaches_the_storage_key(database: str) -> None:
    clinic = world()
    storage = MemoryStorage()
    _upload(clinic, storage, filename="../../escape.pdf")
    assert all("escape" not in key and ".." not in key for key in storage.files)


def test_a_failed_audit_write_leaves_no_row_and_no_file(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic = world()
    storage = MemoryStorage()

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit write failed")

    monkeypatch.setattr("dentacircle.services.document_service.record", fail)
    with pytest.raises(RuntimeError):
        _upload(clinic, storage)
    assert storage.files == {}
    assert _count(Document) == 0
    assert _document_audits() == []


def test_a_failed_commit_leaves_no_row_and_no_file(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinic = world()
    storage = MemoryStorage()

    def fail(self: Session) -> None:
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    with monkeypatch.context() as patched:
        patched.setattr(Session, "commit", fail)
        with pytest.raises(OperationalError):
            _upload(clinic, storage)
    assert storage.files == {}
    assert _count(Document) == 0
    assert _document_audits() == []


def test_the_file_is_stored_before_the_row_is_written(database: str) -> None:
    clinic = world()
    seen: list[int] = []

    class Spy(MemoryStorage):
        def put(self, key: str, data: bytes) -> None:
            with Session(get_engine()) as session:
                seen.append(int(session.scalar(select(func.count()).select_from(Document)) or 0))
            super().put(key, data)

    _upload(clinic, Spy())
    assert seen == [0]
    assert _count(Document) == 1


def test_an_inactive_patient_cannot_receive_a_document(database: str) -> None:
    clinic = world()
    _set_patient_status(clinic.patient_id, "inactive")
    storage = MemoryStorage()
    with pytest.raises(DocumentPatientInactiveError):
        _upload(clinic, storage)
    assert storage.files == {}
    assert _count(Document) == 0
    assert _document_audits() == []


def test_an_unknown_patient_stores_nothing(database: str) -> None:
    clinic = world()
    storage = MemoryStorage()
    with pytest.raises(PatientNotFoundError):
        _upload(clinic, storage, patient_id=uuid4())
    assert storage.files == {}
    assert _count(Document) == 0


def test_another_clinics_patient_is_not_found(database: str) -> None:
    clinic = world()
    other_clinic_id, other_user_id = _other_clinic()
    storage = MemoryStorage()
    with pytest.raises(PatientNotFoundError):
        _upload(clinic, storage, clinic_id=other_clinic_id, actor_id=other_user_id)
    assert storage.files == {}
    assert _count(Document) == 0


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (b"GIF89a....", "image/gif"),
        (_PDF, "image/png"),
        (_PDF, None),
        (b"<script>1</script>", "application/pdf"),
    ],
)
def test_a_wrong_type_stores_nothing(database: str, data: bytes, content_type: str | None) -> None:
    clinic = world()
    storage = MemoryStorage()
    with pytest.raises(UnsupportedMediaTypeError):
        _upload(clinic, storage, data=data, content_type=content_type)
    assert storage.files == {}
    assert _count(Document) == 0
    assert _document_audits() == []


def test_an_empty_file_or_name_stores_nothing(database: str) -> None:
    clinic = world()
    storage = MemoryStorage()
    with pytest.raises(DocumentFieldError):
        _upload(clinic, storage, data=b"")
    with pytest.raises(DocumentFieldError):
        _upload(clinic, storage, filename="  /  ")
    assert storage.files == {}
    assert _count(Document) == 0


def test_a_png_is_accepted(database: str) -> None:
    clinic = world()
    view = _upload(clinic, MemoryStorage(), data=_PNG, content_type="image/png")
    assert view.content_type == "image/png"


# --- read -------------------------------------------------------------------


def test_the_list_is_newest_first_with_paging(database: str) -> None:
    clinic = world()
    storage = MemoryStorage()
    first = _upload(clinic, storage, filename="first.pdf")
    second = _upload(clinic, storage, filename="second.pdf")
    third = _upload(clinic, storage, filename="third.pdf")
    with Session(get_engine()) as session:
        everything = list_documents(session, clinic.clinic_id, clinic.patient_id, 1, 20)
        assert [item.id for item in everything.items] == [third.id, second.id, first.id]
        assert everything.total == 3
        page_two = list_documents(session, clinic.clinic_id, clinic.patient_id, 2, 2)
        assert [item.id for item in page_two.items] == [first.id]
        assert page_two.total == 3
        assert page_two.page == 2
        assert page_two.page_size == 2


def test_an_unknown_or_other_clinic_patient_cannot_be_listed(database: str) -> None:
    clinic = world()
    _upload(clinic, MemoryStorage())
    other_clinic_id, _ = _other_clinic()
    with Session(get_engine()) as session:
        with pytest.raises(PatientNotFoundError):
            list_documents(session, clinic.clinic_id, uuid4(), 1, 20)
        with pytest.raises(PatientNotFoundError):
            list_documents(session, other_clinic_id, clinic.patient_id, 1, 20)


def test_an_inactive_patients_documents_can_be_listed_and_opened(database: str) -> None:
    clinic = world()
    storage = MemoryStorage()
    view = _upload(clinic, storage)
    _set_patient_status(clinic.patient_id, "inactive")
    with Session(get_engine()) as session:
        listed = list_documents(session, clinic.clinic_id, clinic.patient_id, 1, 20)
        assert [item.id for item in listed.items] == [view.id]
        found = open_document(session, storage, clinic.clinic_id, clinic.patient_id, view.id)
        assert b"".join(found.chunks) == _PDF


def test_a_deactivated_uploader_still_has_a_name(database: str) -> None:
    clinic = world()
    _upload(clinic, MemoryStorage())
    with Session(get_engine()) as session:
        user = session.get(AppUser, clinic.actor_id)
        assert user is not None
        user.is_active = False
        session.commit()
    with Session(get_engine()) as session:
        listed = list_documents(session, clinic.clinic_id, clinic.patient_id, 1, 20)
    assert listed.items[0].uploaded_by.name == "Sample Desk"


def test_open_returns_the_view_and_the_bytes(database: str) -> None:
    clinic = world()
    storage = MemoryStorage()
    view = _upload(clinic, storage, data=_PNG, content_type="image/png")
    with Session(get_engine()) as session:
        found = open_document(session, storage, clinic.clinic_id, clinic.patient_id, view.id)
    assert found.view == view
    assert b"".join(found.chunks) == _PNG


def test_a_document_of_another_patient_or_clinic_is_not_found(database: str) -> None:
    clinic = world()
    storage = MemoryStorage()
    view = _upload(clinic, storage)
    other_clinic_id, _ = _other_clinic()
    with Session(get_engine()) as session:
        with pytest.raises(DocumentNotFoundError):
            open_document(session, storage, clinic.clinic_id, uuid4(), view.id)
        with pytest.raises(DocumentNotFoundError):
            open_document(session, storage, clinic.clinic_id, clinic.patient_id, uuid4())
        with pytest.raises(DocumentNotFoundError):
            open_document(session, storage, other_clinic_id, clinic.patient_id, view.id)


def test_a_row_without_its_file_is_not_found_and_the_log_has_no_name(
    database: str, caplog: pytest.LogCaptureFixture
) -> None:
    clinic = world()
    storage = MemoryStorage()
    view = _upload(clinic, storage, filename="distinctive-name.pdf")
    storage.files.clear()
    with caplog.at_level(logging.DEBUG), Session(get_engine()) as session:
        with pytest.raises(DocumentNotFoundError):
            open_document(session, storage, clinic.clinic_id, clinic.patient_id, view.id)
    assert "distinctive-name" not in caplog.text
    assert str(view.id) in caplog.text


def test_reading_writes_no_audit_event(database: str) -> None:
    clinic = world()
    storage = MemoryStorage()
    view = _upload(clinic, storage)
    before = _count(AuditEvent)
    with Session(get_engine()) as session:
        list_documents(session, clinic.clinic_id, clinic.patient_id, 1, 20)
        open_document(session, storage, clinic.clinic_id, clinic.patient_id, view.id)
        session.commit()
    assert _count(AuditEvent) == before
