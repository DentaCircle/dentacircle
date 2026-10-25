"""Care session tables, checks, and composite foreign keys."""

from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import to_psycopg_url
from tests.test_migrations import _config, _public_tables, _version

_ZONE = ZoneInfo("Asia/Kolkata")
_START = datetime(2026, 10, 17, 10, 0, tzinfo=_ZONE)
_END = datetime(2026, 10, 17, 10, 30, tzinfo=_ZONE)

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_USER = "33333333-3333-3333-3333-333333333333"
_OTHER_USER = "44444444-4444-4444-4444-444444444444"
_PATIENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_OTHER_PATIENT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_PLAN = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_ITEM = "dddddddd-dddd-dddd-dddd-dddddddddddd"
_TYPE = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
_VISIT = "ffffffff-ffff-ffff-ffff-ffffffffffff"
_OTHER_VISIT = "12121212-1212-1212-1212-121212121212"
_SESSION = "13131313-1313-1313-1313-131313131313"
_LINE = "14141414-1414-1414-1414-141414141414"


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
    assert _version(throwaway_database_url) == "0019_inventory_transactions"
    assert "care_session" in _public_tables(throwaway_database_url)
    assert "care_session_item" in _public_tables(throwaway_database_url)
    assert _columns(throwaway_database_url, "care_session") == {
        "id",
        "clinic_id",
        "appointment_id",
        "patient_id",
        "recorded_by_user_id",
        "created_at",
    }
    assert _columns(throwaway_database_url, "care_session_item") == {
        "id",
        "clinic_id",
        "care_session_id",
        "care_item_id",
        "status",
        "created_at",
    }
    assert _has_constraint(throwaway_database_url, "uq_appointment_id_clinic_id")
    assert _has_constraint(throwaway_database_url, "uq_care_item_id_clinic_id")

    command.downgrade(config, "0008_care_plans")
    tables = _public_tables(throwaway_database_url)
    assert _version(throwaway_database_url) == "0008_care_plans"
    assert "care_session" not in tables
    assert "care_session_item" not in tables
    assert "care_plan" in tables
    assert "care_item" in tables
    assert not _has_constraint(throwaway_database_url, "uq_appointment_id_clinic_id")
    assert not _has_constraint(throwaway_database_url, "uq_care_item_id_clinic_id")

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0019_inventory_transactions"
    assert "care_session" in _public_tables(throwaway_database_url)
    assert _has_constraint(throwaway_database_url, "uq_appointment_id_clinic_id")
    assert _has_constraint(throwaway_database_url, "uq_care_item_id_clinic_id")


def test_one_session_per_visit_and_known_results(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    _insert_session(db_session, _SESSION, _VISIT, _PATIENT, _USER)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_session(
            db_session,
            "15151515-1515-1515-1515-151515151515",
            _VISIT,
            _PATIENT,
            _USER,
        )
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert_line(db_session, _LINE, _SESSION, _ITEM, "planned")


def test_the_same_item_cannot_appear_twice(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    _insert_session(db_session, _SESSION, _VISIT, _PATIENT, _USER)
    _insert_line(db_session, _LINE, _SESSION, _ITEM, "started")
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_line(
            db_session,
            "16161616-1616-1616-1616-161616161616",
            _SESSION,
            _ITEM,
            "completed",
        )


def test_a_session_cannot_point_outside_its_clinic(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_session(db_session, _SESSION, _OTHER_VISIT, _PATIENT, _USER)
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert_session(db_session, _SESSION, _VISIT, _OTHER_PATIENT, _USER)
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert_session(db_session, _SESSION, _VISIT, _PATIENT, _OTHER_USER)
    db_session.rollback()
    _insert_session(db_session, _SESSION, _VISIT, _PATIENT, _USER)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_line(db_session, _LINE, _SESSION, "17171717-1717-1717-1717-171717171717", "started")


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
    session.execute(
        text(
            "INSERT INTO appointment_type (id, clinic_id, name, duration_minutes)"
            " VALUES (:id, :clinic_id, 'Consultation', 30)"
        ),
        {"id": _TYPE, "clinic_id": _CLINIC},
    )
    session.execute(
        text(
            "INSERT INTO appointment_type (id, clinic_id, name, duration_minutes)"
            " VALUES (:id, :clinic_id, 'Consultation', 30)"
        ),
        {"id": "19191919-1919-1919-1919-191919191919", "clinic_id": _OTHER},
    )
    _visit(session, _CLINIC, _VISIT, _PATIENT, _USER, _TYPE)
    _visit(
        session,
        _OTHER,
        _OTHER_VISIT,
        _OTHER_PATIENT,
        _OTHER_USER,
        "19191919-1919-1919-1919-191919191919",
    )
    session.execute(
        text(
            "INSERT INTO care_plan (id, clinic_id, patient_id, title)"
            " VALUES (:id, :clinic_id, :patient_id, 'Sample plan')"
        ),
        {"id": _PLAN, "clinic_id": _CLINIC, "patient_id": _PATIENT},
    )
    session.execute(
        text(
            "INSERT INTO care_item (id, clinic_id, care_plan_id, name, status)"
            " VALUES (:id, :clinic_id, :plan_id, 'Sample service', 'planned')"
        ),
        {"id": _ITEM, "clinic_id": _CLINIC, "plan_id": _PLAN},
    )
    session.execute(
        text(
            "INSERT INTO care_plan (id, clinic_id, patient_id, title)"
            " VALUES (:id, :clinic_id, :patient_id, 'Other plan')"
        ),
        {
            "id": "18181818-1818-1818-1818-181818181818",
            "clinic_id": _OTHER,
            "patient_id": _OTHER_PATIENT,
        },
    )
    session.execute(
        text(
            "INSERT INTO care_item (id, clinic_id, care_plan_id, name, status)"
            " VALUES (:id, :clinic_id, :plan_id, 'Other service', 'planned')"
        ),
        {
            "id": "17171717-1717-1717-1717-171717171717",
            "clinic_id": _OTHER,
            "plan_id": "18181818-1818-1818-1818-181818181818",
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
            "  :starts_at, :ends_at, 'arrived')"
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


def _insert_session(
    session: Session, session_id: str, visit_id: str, patient_id: str, user_id: str
) -> None:
    clinic_id = _CLINIC
    session.execute(
        text(
            "INSERT INTO care_session"
            " (id, clinic_id, appointment_id, patient_id, recorded_by_user_id)"
            " VALUES (:id, :clinic_id, :visit_id, :patient_id, :user_id)"
        ),
        {
            "id": session_id,
            "clinic_id": clinic_id,
            "visit_id": visit_id,
            "patient_id": patient_id,
            "user_id": user_id,
        },
    )


def _insert_line(
    session: Session, line_id: str, session_id: str, item_id: str, status: str
) -> None:
    session.execute(
        text(
            "INSERT INTO care_session_item"
            " (id, clinic_id, care_session_id, care_item_id, status)"
            " VALUES (:id, :clinic_id, :session_id, :item_id, :status)"
        ),
        {
            "id": line_id,
            "clinic_id": _CLINIC,
            "session_id": session_id,
            "item_id": item_id,
            "status": status,
        },
    )


def _columns(database_url: str, table: str) -> set[str]:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def _has_constraint(database_url: str, name: str) -> bool:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = %s", (name,)
        ).fetchone()
    return row is not None
