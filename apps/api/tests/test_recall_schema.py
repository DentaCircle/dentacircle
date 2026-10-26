"""Recall table, clinic-scoped links, one open row, and the Scaling backfill."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import psycopg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine, to_psycopg_url
from tests.test_migrations import _config, _public_tables, _version

_ZONE = ZoneInfo("Asia/Kolkata")
_START = datetime(2026, 10, 20, 10, 0, tzinfo=_ZONE)
_END = datetime(2026, 10, 20, 10, 30, tzinfo=_ZONE)
_DUE = date(2027, 4, 20)

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_USER = "33333333-3333-3333-3333-333333333333"
_OTHER_USER = "44444444-4444-4444-4444-444444444444"
_PATIENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_OTHER_PATIENT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_TYPE = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
_OTHER_TYPE = "19191919-1919-1919-1919-191919191919"
_VISIT = "ffffffff-ffff-ffff-ffff-ffffffffffff"
_OTHER_VISIT = "12121212-1212-1212-1212-121212121212"
_RECALL = "13131313-1313-1313-1313-131313131313"
_SECOND = "14141414-1414-1414-1414-141414141414"

_FILL_EMPTY_SCALING = (
    "UPDATE appointment_type SET recall_after_months = 6"
    " WHERE recall_after_months IS NULL AND lower(name) = 'scaling'"
)


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
    assert "recall" in _public_tables(throwaway_database_url)
    assert _columns(throwaway_database_url, "recall") == {
        "id",
        "clinic_id",
        "patient_id",
        "appointment_type_id",
        "source_appointment_id",
        "booked_appointment_id",
        "status",
        "due_on",
        "created_at",
    }
    assert "recall_after_months" in _columns(throwaway_database_url, "appointment_type")
    assert _has_index(throwaway_database_url, "uq_recall_open_patient")
    assert _has_index(throwaway_database_url, "ix_recall_clinic_status_due")

    command.downgrade(config, "0012_booked_appointment")
    assert _version(throwaway_database_url) == "0012_booked_appointment"
    assert "recall" not in _public_tables(throwaway_database_url)
    assert "recall_after_months" not in _columns(throwaway_database_url, "appointment_type")
    assert "follow_up" in _public_tables(throwaway_database_url)

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0019_inventory_transactions"
    assert "recall" in _public_tables(throwaway_database_url)


def test_existing_scaling_is_filled_only_when_empty(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    clear_engine()
    config = _config()
    command.upgrade(config, "0012_booked_appointment")
    with Session(get_engine()) as session:
        _clinic(session, _CLINIC)
        _clinic(session, _OTHER)
        _type(session, _TYPE, _CLINIC, "Scaling")
        _type(session, _OTHER_TYPE, _OTHER, "SCALING")
        _type(session, _VISIT, _CLINIC, "Consultation")
        session.commit()

    command.upgrade(config, "head")
    assert _months(throwaway_database_url, _TYPE) == 6
    assert _months(throwaway_database_url, _OTHER_TYPE) == 6
    assert _months(throwaway_database_url, _VISIT) is None

    with psycopg.connect(to_psycopg_url(throwaway_database_url)) as connection:
        connection.execute(
            "UPDATE appointment_type SET recall_after_months = 12 WHERE id = %s",
            (_TYPE,),
        )
        connection.execute(
            "UPDATE appointment_type SET recall_after_months = NULL WHERE id = %s",
            (_OTHER_TYPE,),
        )
        connection.execute(_FILL_EMPTY_SCALING)
    assert _months(throwaway_database_url, _TYPE) == 12
    assert _months(throwaway_database_url, _OTHER_TYPE) == 6


def test_the_interval_must_be_empty_or_from_one_to_sixty(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    for months in (0, 61):
        with pytest.raises(IntegrityError):
            db_session.execute(
                text("UPDATE appointment_type SET recall_after_months = :months WHERE id = :id"),
                {"months": months, "id": _TYPE},
            )
        db_session.rollback()
    db_session.execute(
        text("UPDATE appointment_type SET recall_after_months = 1 WHERE id = :id"),
        {"id": _TYPE},
    )
    db_session.commit()
    db_session.execute(
        text("UPDATE appointment_type SET recall_after_months = 60 WHERE id = :id"),
        {"id": _TYPE},
    )
    db_session.commit()


def test_status_defaults_to_scheduled_and_one_open_row_per_patient(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert(db_session, _RECALL, _CLINIC, _PATIENT, _TYPE, _VISIT, status=None)
    status: str = db_session.execute(
        text("SELECT status FROM recall WHERE id = :id"), {"id": _RECALL}
    ).scalar_one()
    assert status == "scheduled"
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(db_session, _SECOND, _CLINIC, _PATIENT, _TYPE, _VISIT, status="done")
    db_session.rollback()
    for status_name in ("scheduled", "contacted", "booked"):
        with pytest.raises(IntegrityError):
            _insert(db_session, _SECOND, _CLINIC, _PATIENT, _TYPE, _VISIT, status=status_name)
        db_session.rollback()
    db_session.execute(
        text("UPDATE recall SET status = 'completed' WHERE id = :id"), {"id": _RECALL}
    )
    db_session.commit()
    _insert(db_session, _SECOND, _CLINIC, _PATIENT, _TYPE, _VISIT, status="scheduled")
    db_session.commit()


def test_a_recall_cannot_point_outside_its_clinic(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(db_session, _RECALL, _CLINIC, _OTHER_PATIENT, _TYPE, _VISIT, status="scheduled")
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert(db_session, _RECALL, _CLINIC, _PATIENT, _OTHER_TYPE, _VISIT, status="scheduled")
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert(db_session, _RECALL, _CLINIC, _PATIENT, _TYPE, _OTHER_VISIT, status="scheduled")
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert(
            db_session,
            _RECALL,
            _CLINIC,
            _PATIENT,
            _TYPE,
            _VISIT,
            status="booked",
            booked_appointment_id=_OTHER_VISIT,
        )


def _months(database_url: str, type_id: str) -> int | None:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT recall_after_months FROM appointment_type WHERE id = %s",
            (type_id,),
        ).fetchone()
    assert row is not None
    value = row[0]
    if value is None:
        return None
    return int(value)


def _columns(database_url: str, table: str) -> set[str]:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def _has_index(database_url: str, name: str) -> bool:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT 1 FROM pg_indexes WHERE indexname = %s", (name,)
        ).fetchone()
    return row is not None


def _seed(session: Session) -> None:
    _clinic(session, _CLINIC)
    _clinic(session, _OTHER)
    _user(session, _CLINIC, _USER, "a@x.test")
    _user(session, _OTHER, _OTHER_USER, "b@x.test")
    _patient(session, _CLINIC, _PATIENT)
    _patient(session, _OTHER, _OTHER_PATIENT)
    _type(session, _TYPE, _CLINIC, "Scaling")
    _type(session, _OTHER_TYPE, _OTHER, "Scaling")
    _visit(session, _CLINIC, _VISIT, _PATIENT, _USER, _TYPE)
    _visit(session, _OTHER, _OTHER_VISIT, _OTHER_PATIENT, _OTHER_USER, _OTHER_TYPE)


def _clinic(session: Session, clinic_id: str) -> None:
    session.execute(
        text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
        {"id": clinic_id},
    )


def _user(session: Session, clinic_id: str, user_id: str, email: str) -> None:
    session.execute(
        text(
            "INSERT INTO app_user (id, clinic_id, email, full_name, password_hash)"
            " VALUES (:id, :clinic_id, :email, 'Synthetic Person', 'hash')"
        ),
        {"id": user_id, "clinic_id": clinic_id, "email": email},
    )


def _patient(session: Session, clinic_id: str, patient_id: str) -> None:
    session.execute(
        text(
            "INSERT INTO patient"
            " (id, clinic_id, patient_number, full_name, phone, phone_digits)"
            " VALUES (:id, :clinic_id, 1, 'Sample', '9000000001', '9000000001')"
        ),
        {"id": patient_id, "clinic_id": clinic_id},
    )


def _type(session: Session, type_id: str, clinic_id: str, name: str) -> None:
    session.execute(
        text(
            "INSERT INTO appointment_type (id, clinic_id, name, duration_minutes)"
            " VALUES (:id, :clinic_id, :name, 30)"
        ),
        {"id": type_id, "clinic_id": clinic_id, "name": name},
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
            "  :starts_at, :ends_at, 'completed')"
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


def _insert(
    session: Session,
    recall_id: str,
    clinic_id: str,
    patient_id: str,
    type_id: str,
    visit_id: str,
    status: str | None,
    booked_appointment_id: str | None = None,
) -> None:
    if status is None:
        session.execute(
            text(
                "INSERT INTO recall"
                " (id, clinic_id, patient_id, appointment_type_id, source_appointment_id, due_on)"
                " VALUES (:id, :clinic_id, :patient_id, :type_id, :visit_id, :due_on)"
            ),
            {
                "id": recall_id,
                "clinic_id": clinic_id,
                "patient_id": patient_id,
                "type_id": type_id,
                "visit_id": visit_id,
                "due_on": _DUE,
            },
        )
        return
    session.execute(
        text(
            "INSERT INTO recall"
            " (id, clinic_id, patient_id, appointment_type_id, source_appointment_id,"
            "  status, due_on, booked_appointment_id)"
            " VALUES (:id, :clinic_id, :patient_id, :type_id, :visit_id,"
            "  :status, :due_on, :booked)"
        ),
        {
            "id": recall_id,
            "clinic_id": clinic_id,
            "patient_id": patient_id,
            "type_id": type_id,
            "visit_id": visit_id,
            "status": status,
            "due_on": _DUE,
            "booked": booked_appointment_id,
        },
    )
