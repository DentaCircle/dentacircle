"""Document table: checks, clinic-scoped links, the unique key and rollback."""

from uuid import uuid4

import psycopg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import to_psycopg_url
from dentacircle.domain.document import MAX_DOCUMENT_BYTES
from tests.test_migrations import _config, _public_tables, _version

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_USER = "33333333-3333-3333-3333-333333333333"
_OTHER_USER = "44444444-4444-4444-4444-444444444444"
_PATIENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_OTHER_PATIENT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

_COLUMNS = {
    "id",
    "clinic_id",
    "patient_id",
    "uploaded_by_user_id",
    "filename",
    "content_type",
    "size_bytes",
    "storage_key",
    "appointment_id",
    "follow_up_id",
    "lab_work_id",
    "created_at",
}


@pytest.fixture
def migrated(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    return throwaway_database_url


def test_upgrade_downgrade_upgrade(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = _config()
    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0018_inventory"
    assert "document" in _public_tables(throwaway_database_url)
    assert _columns(throwaway_database_url) == _COLUMNS
    assert "DESC" in _index_def(throwaway_database_url)

    command.downgrade(config, "0014_timeline")
    assert _version(throwaway_database_url) == "0014_timeline"
    assert "document" not in _public_tables(throwaway_database_url)
    assert "timeline_event" in _public_tables(throwaway_database_url)

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0018_inventory"
    assert "document" in _public_tables(throwaway_database_url)


def test_a_valid_row_is_stored(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    _insert(db_session)
    db_session.commit()
    count: int = db_session.execute(text("SELECT count(*) FROM document")).scalar_one()
    assert count == 1


@pytest.mark.parametrize("filename", ["", "x" * 201])
def test_the_filename_must_be_one_to_two_hundred_characters(
    migrated: str, db_session: Session, filename: str
) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(db_session, filename=filename)


def test_a_two_hundred_character_name_is_stored(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    _insert(db_session, filename="x" * 200)


@pytest.mark.parametrize("content_type", ["image/gif", "text/html", "application/PDF", ""])
def test_the_content_type_must_be_one_of_the_three(
    migrated: str, db_session: Session, content_type: str
) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(db_session, content_type=content_type)


@pytest.mark.parametrize("size", [0, -1, MAX_DOCUMENT_BYTES + 1])
def test_the_size_must_be_in_range(migrated: str, db_session: Session, size: int) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(db_session, size_bytes=size)


def test_the_size_limits_themselves_are_stored(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    _insert(db_session, size_bytes=1)
    _insert(db_session, size_bytes=MAX_DOCUMENT_BYTES)


def test_the_storage_key_is_unique(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    _insert(db_session, storage_key="same-key")
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(db_session, storage_key="same-key")


def test_a_document_cannot_point_at_another_clinics_patient_or_user(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(db_session, patient_id=_OTHER_PATIENT)
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert(db_session, uploaded_by_user_id=_OTHER_USER)


def test_id_and_clinic_are_unique_together_for_later_links(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    document_id = _insert(db_session)
    db_session.commit()
    names: set[str] = set(
        db_session.execute(
            text(
                "SELECT conname FROM pg_constraint"
                " WHERE conrelid = 'document'::regclass AND contype = 'u'"
            )
        ).scalars()
    )
    assert "uq_document_id_clinic_id" in names
    assert document_id


def test_the_list_index_orders_newest_first(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    first = _insert(db_session)
    second = _insert(db_session)
    db_session.commit()
    db_session.execute(
        text("UPDATE document SET created_at = created_at - interval '1 hour' WHERE id = :id"),
        {"id": first},
    )
    query = text("SELECT id FROM document ORDER BY created_at DESC, id DESC")
    ids: list[str] = [str(found) for found in db_session.scalars(query)]
    assert ids == [second, first]


def _columns(database_url: str) -> set[str]:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = 'document'"
        ).fetchall()
    return {str(row[0]) for row in rows}


def _index_def(database_url: str) -> str:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_document_patient_order'"
        ).fetchone()
    assert row is not None
    return str(row[0])


def _insert(
    session: Session,
    *,
    patient_id: str = _PATIENT,
    uploaded_by_user_id: str = _USER,
    filename: str = "report.pdf",
    content_type: str = "application/pdf",
    size_bytes: int = 10,
    storage_key: str | None = None,
) -> str:
    document_id = str(uuid4())
    session.execute(
        text(
            "INSERT INTO document (id, clinic_id, patient_id, uploaded_by_user_id,"
            " filename, content_type, size_bytes, storage_key)"
            " VALUES (:id, :clinic_id, :patient_id, :user_id,"
            " :filename, :content_type, :size_bytes, :storage_key)"
        ),
        {
            "id": document_id,
            "clinic_id": _CLINIC,
            "patient_id": patient_id,
            "user_id": uploaded_by_user_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "storage_key": storage_key if storage_key is not None else f"{_CLINIC}/{document_id}",
        },
    )
    return document_id


def _seed(session: Session) -> None:
    for clinic_id in (_CLINIC, _OTHER):
        session.execute(
            text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
            {"id": clinic_id},
        )
    for clinic_id, user_id, email in (
        (_CLINIC, _USER, "a@x.test"),
        (_OTHER, _OTHER_USER, "b@x.test"),
    ):
        session.execute(
            text(
                "INSERT INTO app_user (id, clinic_id, email, full_name, password_hash)"
                " VALUES (:id, :clinic_id, :email, 'Synthetic Person', 'hash')"
            ),
            {"id": user_id, "clinic_id": clinic_id, "email": email},
        )
    for clinic_id, patient_id in ((_CLINIC, _PATIENT), (_OTHER, _OTHER_PATIENT)):
        session.execute(
            text(
                "INSERT INTO patient"
                " (id, clinic_id, patient_number, full_name, phone, phone_digits)"
                " VALUES (:id, :clinic_id, 1, 'Sample', '9000000001', '9000000001')"
            ),
            {"id": patient_id, "clinic_id": clinic_id},
        )
