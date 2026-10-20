"""Timeline table: kinds, one subject, clinic-scoped links, seq, and rollback."""

import inspect
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import to_psycopg_url
from dentacircle.domain.timeline import TIMELINE_KINDS, subject_column
from dentacircle.repositories.timeline_repository import TimelineRepository
from tests.test_migrations import _config, _public_tables, _version

_ZONE = ZoneInfo("Asia/Kolkata")
_START = datetime(2026, 10, 12, 10, 0, tzinfo=_ZONE)
_END = datetime(2026, 10, 12, 10, 30, tzinfo=_ZONE)
_DUE = "2026-10-19"

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_USER = "33333333-3333-3333-3333-333333333333"
_OTHER_USER = "44444444-4444-4444-4444-444444444444"
_PATIENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_OTHER_PATIENT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_TYPE = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
_VISIT = "ffffffff-ffff-ffff-ffff-ffffffffffff"
_OTHER_VISIT = "12121212-1212-1212-1212-121212121212"
_OTHER_TYPE = "20202020-2020-2020-2020-202020202020"
_PLAN = "15151515-1515-1515-1515-151515151515"
_ITEM = "16161616-1616-1616-1616-161616161616"
_SESSION = "17171717-1717-1717-1717-171717171717"
_FOLLOW_UP = "18181818-1818-1818-1818-181818181818"
_RECALL = "19191919-1919-1919-1919-191919191919"

_COLUMNS = {
    "id",
    "seq",
    "clinic_id",
    "patient_id",
    "actor_user_id",
    "kind",
    "occurred_at",
    "appointment_id",
    "care_item_id",
    "care_session_id",
    "follow_up_id",
    "recall_id",
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
    assert _version(throwaway_database_url) == "0014_timeline"
    assert "timeline_event" in _public_tables(throwaway_database_url)
    assert _columns(throwaway_database_url) == _COLUMNS
    assert "DESC" in _index_def(throwaway_database_url)

    command.downgrade(config, "0013_recalls")
    assert _version(throwaway_database_url) == "0013_recalls"
    assert "timeline_event" not in _public_tables(throwaway_database_url)
    assert "recall" in _public_tables(throwaway_database_url)

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0014_timeline"
    assert "timeline_event" in _public_tables(throwaway_database_url)


def test_each_kind_needs_its_one_subject(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    for kind in TIMELINE_KINDS:
        _insert(db_session, kind, **_subject_for(kind))
    db_session.commit()
    stored: set[str] = set(db_session.execute(text("SELECT kind FROM timeline_event")).scalars())
    assert stored == set(TIMELINE_KINDS)

    with pytest.raises(IntegrityError):
        _insert(db_session, "not_a_kind")
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert(db_session, "visit_booked", care_item_id=_ITEM)
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert(db_session, "patient_registered", appointment_id=_VISIT)
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert(db_session, "visit_booked", appointment_id=_VISIT, follow_up_id=_FOLLOW_UP)


def test_a_subject_cannot_point_at_another_clinic(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(db_session, "visit_booked", appointment_id=_OTHER_VISIT)
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert(db_session, "patient_registered", patient_id=_OTHER_PATIENT)
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert(db_session, "patient_registered", actor_user_id=_OTHER_USER)


def test_seq_keeps_write_order_when_the_time_matches(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    first = _insert(db_session, "patient_registered")
    second = _insert(db_session, "patient_registered")
    db_session.commit()
    rows = list(
        db_session.execute(
            text("SELECT id, seq FROM timeline_event ORDER BY occurred_at DESC, seq DESC")
        )
    )
    assert [str(row[0]) for row in rows] == [second, first]
    assert rows[0][1] > rows[1][1]


def test_a_failed_event_write_rolls_back_the_change(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE patient SET full_name = 'Changed Name' WHERE id = :id"),
            {"id": _PATIENT},
        )
        _insert(db_session, "not_a_kind")
        db_session.flush()
    db_session.rollback()
    name: str = db_session.execute(
        text("SELECT full_name FROM patient WHERE id = :id"), {"id": _PATIENT}
    ).scalar_one()
    count: int = db_session.execute(text("SELECT count(*) FROM timeline_event")).scalar_one()
    assert name == "Sample"
    assert count == 0


def test_the_repository_does_not_update_or_delete() -> None:
    names = {
        name
        for name, value in inspect.getmembers(TimelineRepository, inspect.isfunction)
        if not name.startswith("_")
    }
    assert "add" in names
    assert "list_for_patient" in names
    assert "update" not in names
    assert "delete" not in names


def _subject_for(kind: str) -> dict[str, str]:
    column = subject_column(kind)
    if column is None:
        return {}
    ids = {
        "appointment_id": _VISIT,
        "care_item_id": _ITEM,
        "care_session_id": _SESSION,
        "follow_up_id": _FOLLOW_UP,
        "recall_id": _RECALL,
    }
    return {column: ids[column]}


def _insert(
    session: Session,
    kind: str,
    *,
    patient_id: str = _PATIENT,
    actor_user_id: str = _USER,
    appointment_id: str | None = None,
    care_item_id: str | None = None,
    care_session_id: str | None = None,
    follow_up_id: str | None = None,
    recall_id: str | None = None,
) -> str:
    event_id = str(uuid4())
    session.execute(
        text(
            "INSERT INTO timeline_event"
            " (id, clinic_id, patient_id, actor_user_id, kind,"
            "  appointment_id, care_item_id, care_session_id, follow_up_id, recall_id)"
            " VALUES (:id, :clinic_id, :patient_id, :actor_user_id, :kind,"
            "  :appointment_id, :care_item_id, :care_session_id, :follow_up_id, :recall_id)"
        ),
        {
            "id": event_id,
            "clinic_id": _CLINIC,
            "patient_id": patient_id,
            "actor_user_id": actor_user_id,
            "kind": kind,
            "appointment_id": appointment_id,
            "care_item_id": care_item_id,
            "care_session_id": care_session_id,
            "follow_up_id": follow_up_id,
            "recall_id": recall_id,
        },
    )
    return event_id


def _seed(session: Session) -> None:
    for clinic_id in (_CLINIC, _OTHER):
        session.execute(
            text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
            {"id": clinic_id},
        )
    _user(session, _CLINIC, _USER, "a@x.test")
    _user(session, _OTHER, _OTHER_USER, "b@x.test")
    _patient(session, _CLINIC, _PATIENT, 1)
    _patient(session, _OTHER, _OTHER_PATIENT, 1)
    for clinic_id, type_id in ((_CLINIC, _TYPE), (_OTHER, _OTHER_TYPE)):
        session.execute(
            text(
                "INSERT INTO appointment_type (id, clinic_id, name, duration_minutes)"
                " VALUES (:id, :clinic_id, 'Consultation', 30)"
            ),
            {"id": type_id, "clinic_id": clinic_id},
        )
    _visit(session, _CLINIC, _VISIT, _PATIENT, _USER, _TYPE)
    _visit(session, _OTHER, _OTHER_VISIT, _OTHER_PATIENT, _OTHER_USER, _OTHER_TYPE)
    session.execute(
        text(
            "INSERT INTO care_plan (id, clinic_id, patient_id, title)"
            " VALUES (:id, :clinic_id, :patient_id, 'Sample plan')"
        ),
        {"id": _PLAN, "clinic_id": _CLINIC, "patient_id": _PATIENT},
    )
    session.execute(
        text(
            "INSERT INTO care_item (id, clinic_id, care_plan_id, name)"
            " VALUES (:id, :clinic_id, :plan_id, 'Sample service')"
        ),
        {"id": _ITEM, "clinic_id": _CLINIC, "plan_id": _PLAN},
    )
    session.execute(
        text(
            "INSERT INTO care_session"
            " (id, clinic_id, appointment_id, patient_id, recorded_by_user_id)"
            " VALUES (:id, :clinic_id, :visit_id, :patient_id, :user_id)"
        ),
        {
            "id": _SESSION,
            "clinic_id": _CLINIC,
            "visit_id": _VISIT,
            "patient_id": _PATIENT,
            "user_id": _USER,
        },
    )
    session.execute(
        text(
            "INSERT INTO follow_up (id, clinic_id, patient_id, appointment_id, status, due_on)"
            " VALUES (:id, :clinic_id, :patient_id, :visit_id, 'scheduled', :due_on)"
        ),
        {
            "id": _FOLLOW_UP,
            "clinic_id": _CLINIC,
            "patient_id": _PATIENT,
            "visit_id": _VISIT,
            "due_on": _DUE,
        },
    )
    session.execute(
        text(
            "INSERT INTO recall"
            " (id, clinic_id, patient_id, appointment_type_id, source_appointment_id,"
            "  status, due_on)"
            " VALUES (:id, :clinic_id, :patient_id, :type_id, :visit_id, 'scheduled', :due_on)"
        ),
        {
            "id": _RECALL,
            "clinic_id": _CLINIC,
            "patient_id": _PATIENT,
            "type_id": _TYPE,
            "visit_id": _VISIT,
            "due_on": _DUE,
        },
    )


def _user(session: Session, clinic_id: str, user_id: str, email: str) -> None:
    session.execute(
        text(
            "INSERT INTO app_user (id, clinic_id, email, full_name, password_hash)"
            " VALUES (:id, :clinic_id, :email, 'Synthetic Person', 'hash')"
        ),
        {"id": user_id, "clinic_id": clinic_id, "email": email},
    )


def _patient(session: Session, clinic_id: str, patient_id: str, number: int) -> None:
    session.execute(
        text(
            "INSERT INTO patient"
            " (id, clinic_id, patient_number, full_name, phone, phone_digits)"
            " VALUES (:id, :clinic_id, :number, 'Sample', '9000000001', '9000000001')"
        ),
        {"id": patient_id, "clinic_id": clinic_id, "number": number},
    )


def _visit(
    session: Session,
    clinic_id: str,
    visit_id: str,
    patient_id: str,
    user_id: str,
    type_id: str,
) -> None:
    session.execute(
        text(
            "INSERT INTO appointment"
            " (id, clinic_id, patient_id, clinician_user_id, appointment_type_id,"
            "  starts_at, ends_at, status)"
            " VALUES (:id, :clinic_id, :patient_id, :user_id, :type_id,"
            "  :starts_at, :ends_at, 'scheduled')"
        ),
        {
            "id": visit_id,
            "clinic_id": clinic_id,
            "patient_id": patient_id,
            "user_id": user_id,
            "type_id": type_id,
            "starts_at": _START,
            "ends_at": _END,
        },
    )


def _columns(database_url: str) -> set[str]:
    import psycopg

    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = 'timeline_event'"
        ).fetchall()
    return {row[0] for row in rows}


def _index_def(database_url: str) -> str:
    import psycopg

    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_timeline_event_patient_order'"
        ).fetchone()
    assert row is not None
    return str(row[0])
