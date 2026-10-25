"""Lab work table, the document link, and the lab timeline subject check."""

from uuid import uuid4

import psycopg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine, to_psycopg_url
from tests.test_migrations import _config, _public_tables, _version

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_USER = "33333333-3333-3333-3333-333333333333"
_PATIENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_OTHER_PATIENT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_LAB = "23232323-2323-2323-2323-232323232323"

_COLUMNS = {
    "id",
    "clinic_id",
    "patient_id",
    "appointment_id",
    "title",
    "expected_on",
    "status",
    "created_by_user_id",
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
    assert "lab_work" in _public_tables(throwaway_database_url)
    assert _columns(throwaway_database_url, "lab_work") == _COLUMNS
    assert "lab_work_id" in _columns(throwaway_database_url, "document")
    assert "lab_work_id" in _columns(throwaway_database_url, "timeline_event")
    assert "DESC" in _index_def(throwaway_database_url)

    command.downgrade(config, "0016_document_links")
    assert _version(throwaway_database_url) == "0016_document_links"
    assert "lab_work" not in _public_tables(throwaway_database_url)
    assert "lab_work_id" not in _columns(throwaway_database_url, "document")
    assert "lab_work_id" not in _columns(throwaway_database_url, "timeline_event")
    assert "document" in _public_tables(throwaway_database_url)

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0018_inventory"
    assert "lab_work" in _public_tables(throwaway_database_url)


def test_downgrade_deletes_lab_timeline_rows_and_clears_the_document_link(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = _config()
    command.upgrade(config, "head")
    clear_engine()
    with Session(get_engine()) as session:
        _seed(session)
        lab_id = _insert_lab(session)
        kept = _insert_event(session, "patient_registered")
        _insert_event(session, "lab_work_created", lab_work_id=lab_id)
        document_id = _insert_document(session, lab_work_id=lab_id)
        session.commit()
    command.downgrade(config, "0016_document_links")
    assert "lab_work_id" not in _columns(throwaway_database_url, "document")
    clear_engine()
    with Session(get_engine()) as session:
        kinds = list(session.scalars(text("SELECT kind FROM timeline_event")))
        ids = list(session.scalars(text("SELECT id::text FROM timeline_event")))
        documents = list(session.scalars(text("SELECT id::text FROM document")))
    assert kinds == ["patient_registered"]
    assert ids == [kept]
    assert documents == [document_id]


@pytest.mark.parametrize("title", ["", "x" * 201])
def test_the_title_must_be_one_to_two_hundred_characters(
    migrated: str, db_session: Session, title: str
) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_lab(db_session, title=title)


@pytest.mark.parametrize("status", ["sent", "in_progress", ""])
def test_the_status_must_be_one_of_the_four(
    migrated: str, db_session: Session, status: str
) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_lab(db_session, status=status)


def test_a_lab_kind_needs_its_one_subject(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    lab_id = _insert_lab(db_session)
    db_session.commit()
    _insert_event(db_session, "lab_work_ready", lab_work_id=lab_id)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_event(db_session, "lab_work_created")
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert_event(db_session, "lab_work_created", lab_work_id=lab_id, extra_document=True)


def test_a_lab_item_cannot_point_at_another_clinics_patient(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_lab(db_session, patient_id=_OTHER_PATIENT)


def _columns(database_url: str, table: str) -> set[str]:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    return {str(row[0]) for row in rows}


def _index_def(database_url: str) -> str:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_lab_work_patient_order'"
        ).fetchone()
    assert row is not None
    return str(row[0])


def _seed(session: Session) -> None:
    for clinic_id in (_CLINIC, _OTHER):
        session.execute(
            text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
            {"id": clinic_id},
        )
    session.execute(
        text(
            "INSERT INTO app_user (id, clinic_id, email, full_name, password_hash)"
            " VALUES (:id, :clinic_id, 'a@x.test', 'Synthetic Person', 'hash')"
        ),
        {"id": _USER, "clinic_id": _CLINIC},
    )
    session.execute(
        text(
            "INSERT INTO patient"
            " (id, clinic_id, patient_number, full_name, phone, phone_digits)"
            " VALUES (:id, :clinic_id, 1, 'Sample', '9000000001', '9000000001')"
        ),
        {"id": _PATIENT, "clinic_id": _CLINIC},
    )
    session.execute(
        text(
            "INSERT INTO patient"
            " (id, clinic_id, patient_number, full_name, phone, phone_digits)"
            " VALUES (:id, :clinic_id, 1, 'Sample', '9000000002', '9000000002')"
        ),
        {"id": _OTHER_PATIENT, "clinic_id": _OTHER},
    )


def _insert_lab(
    session: Session,
    *,
    patient_id: str = _PATIENT,
    title: str = "Crown",
    status: str = "pending",
) -> str:
    lab_id = str(uuid4())
    session.execute(
        text(
            "INSERT INTO lab_work"
            " (id, clinic_id, patient_id, title, status, created_by_user_id)"
            " VALUES (:id, :clinic_id, :patient_id, :title, :status, :user_id)"
        ),
        {
            "id": lab_id,
            "clinic_id": _CLINIC,
            "patient_id": patient_id,
            "title": title,
            "status": status,
            "user_id": _USER,
        },
    )
    return lab_id


def _insert_document(session: Session, *, lab_work_id: str) -> str:
    document_id = str(uuid4())
    session.execute(
        text(
            "INSERT INTO document"
            " (id, clinic_id, patient_id, uploaded_by_user_id, filename, content_type,"
            "  size_bytes, storage_key, lab_work_id)"
            " VALUES (:id, :clinic_id, :patient_id, :user_id, 'result.png', 'image/png',"
            "  10, :storage_key, :lab_work_id)"
        ),
        {
            "id": document_id,
            "clinic_id": _CLINIC,
            "patient_id": _PATIENT,
            "user_id": _USER,
            "storage_key": f"{_CLINIC}/{document_id}",
            "lab_work_id": lab_work_id,
        },
    )
    return document_id


def _insert_event(
    session: Session,
    kind: str,
    *,
    lab_work_id: str | None = None,
    extra_document: bool = False,
) -> str:
    event_id = str(uuid4())
    document_id = None
    if extra_document:
        document_id = _insert_document(session, lab_work_id=lab_work_id or _LAB)
    session.execute(
        text(
            "INSERT INTO timeline_event"
            " (id, clinic_id, patient_id, actor_user_id, kind, lab_work_id, document_id)"
            " VALUES (:id, :clinic_id, :patient_id, :user_id, :kind, :lab_work_id, :document_id)"
        ),
        {
            "id": event_id,
            "clinic_id": _CLINIC,
            "patient_id": _PATIENT,
            "user_id": _USER,
            "kind": kind,
            "lab_work_id": lab_work_id,
            "document_id": document_id,
        },
    )
    return event_id
