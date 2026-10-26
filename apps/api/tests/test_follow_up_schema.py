"""Follow-up table, checks, and the one-open-row rule."""

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
_START = datetime(2026, 10, 17, 10, 0, tzinfo=_ZONE)
_END = datetime(2026, 10, 17, 10, 30, tzinfo=_ZONE)
_DUE = date(2026, 10, 24)

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
_FOLLOW_UP = "13131313-1313-1313-1313-131313131313"
_SECOND = "14141414-1414-1414-1414-141414141414"


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
    assert "follow_up" in _public_tables(throwaway_database_url)
    assert _columns(throwaway_database_url, "follow_up") == {
        "id",
        "clinic_id",
        "patient_id",
        "appointment_id",
        "booked_appointment_id",
        "status",
        "due_on",
        "created_at",
    }
    assert _has_index(throwaway_database_url, "uq_follow_up_open_patient")
    assert _has_index(throwaway_database_url, "ix_follow_up_clinic_status_due")

    command.downgrade(config, "0009_care_sessions")
    assert _version(throwaway_database_url) == "0009_care_sessions"
    assert "follow_up" not in _public_tables(throwaway_database_url)
    assert "care_session" in _public_tables(throwaway_database_url)

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0019_inventory_transactions"
    assert "follow_up" in _public_tables(throwaway_database_url)


def test_status_must_be_one_of_five_and_defaults_to_scheduled(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert(db_session, _FOLLOW_UP, _CLINIC, _PATIENT, _VISIT, status=None, due_on=_DUE)
    status: str = db_session.execute(
        text("SELECT status FROM follow_up WHERE id = :id"), {"id": _FOLLOW_UP}
    ).scalar_one()
    assert status == "scheduled"
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(db_session, _SECOND, _CLINIC, _PATIENT, _VISIT, status="done", due_on=_DUE)


def test_one_open_follow_up_per_patient_and_a_closed_one_allows_another(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert(db_session, _FOLLOW_UP, _CLINIC, _PATIENT, _VISIT, status="scheduled", due_on=_DUE)
    db_session.commit()
    for status in ("scheduled", "contacted", "booked"):
        with pytest.raises(IntegrityError):
            _insert(db_session, _SECOND, _CLINIC, _PATIENT, _VISIT, status=status, due_on=_DUE)
        db_session.rollback()
    db_session.execute(
        text("UPDATE follow_up SET status = 'completed' WHERE id = :id"), {"id": _FOLLOW_UP}
    )
    db_session.commit()
    _insert(db_session, _SECOND, _CLINIC, _PATIENT, _VISIT, status="scheduled", due_on=_DUE)
    db_session.commit()
    db_session.execute(text("DELETE FROM follow_up WHERE id = :id"), {"id": _SECOND})
    db_session.execute(
        text("UPDATE follow_up SET status = 'cancelled' WHERE id = :id"), {"id": _FOLLOW_UP}
    )
    db_session.commit()
    _insert(db_session, _SECOND, _CLINIC, _PATIENT, _VISIT, status="booked", due_on=_DUE)


def test_appointment_id_is_nullable_and_downgrade_refuses_a_null(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    clear_engine()
    config = _config()
    command.upgrade(config, "0010_follow_ups")
    assert _version(throwaway_database_url) == "0010_follow_ups"
    assert _appointment_nullable(throwaway_database_url) is False

    command.upgrade(config, "0011_null_visit")
    assert _appointment_nullable(throwaway_database_url) is True
    with Session(get_engine()) as session:
        _seed(session)
        _insert(session, _FOLLOW_UP, _CLINIC, _PATIENT, None, status="scheduled", due_on=_DUE)
        session.commit()
    with pytest.raises(RuntimeError, match="no visit"):
        command.downgrade(config, "0010_follow_ups")
    assert _version(throwaway_database_url) == "0011_null_visit"
    assert _appointment_nullable(throwaway_database_url) is True

    with Session(get_engine()) as session:
        session.execute(
            text("UPDATE follow_up SET appointment_id = :visit WHERE id = :id"),
            {"visit": _VISIT, "id": _FOLLOW_UP},
        )
        session.commit()
    command.downgrade(config, "0010_follow_ups")
    assert _version(throwaway_database_url) == "0010_follow_ups"
    assert _appointment_nullable(throwaway_database_url) is False
    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0019_inventory_transactions"
    assert _appointment_nullable(throwaway_database_url) is True


def test_booked_appointment_column_upgrades_and_downgrades(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    clear_engine()
    config = _config()
    command.upgrade(config, "0011_null_visit")
    assert "booked_appointment_id" not in _columns(throwaway_database_url, "follow_up")
    command.upgrade(config, "0012_booked_appointment")
    assert "booked_appointment_id" in _columns(throwaway_database_url, "follow_up")
    command.downgrade(config, "0011_null_visit")
    assert "booked_appointment_id" not in _columns(throwaway_database_url, "follow_up")
    command.upgrade(config, "head")
    assert "booked_appointment_id" in _columns(throwaway_database_url, "follow_up")
    assert _version(throwaway_database_url) == "0019_inventory_transactions"


def test_booked_appointment_cannot_point_outside_its_clinic(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(
            db_session,
            _FOLLOW_UP,
            _CLINIC,
            _PATIENT,
            _VISIT,
            status="booked",
            due_on=_DUE,
            booked_appointment_id=_OTHER_VISIT,
        )


def test_a_follow_up_cannot_point_outside_its_clinic(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert(
            db_session,
            _FOLLOW_UP,
            _CLINIC,
            _OTHER_PATIENT,
            _VISIT,
            status="scheduled",
            due_on=_DUE,
        )
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _insert(
            db_session, _FOLLOW_UP, _CLINIC, _PATIENT, _OTHER_VISIT, status="scheduled", due_on=_DUE
        )


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
        {"id": _OTHER_TYPE, "clinic_id": _OTHER},
    )
    _visit(session, _CLINIC, _VISIT, _PATIENT, _USER, _TYPE)
    _visit(session, _OTHER, _OTHER_VISIT, _OTHER_PATIENT, _OTHER_USER, _OTHER_TYPE)


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
            "  :starts_at, :ends_at, 'in_progress')"
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
    follow_up_id: str,
    clinic_id: str,
    patient_id: str,
    visit_id: str | None,
    status: str | None,
    due_on: date,
    booked_appointment_id: str | None = None,
) -> None:
    if status is None:
        session.execute(
            text(
                "INSERT INTO follow_up"
                " (id, clinic_id, patient_id, appointment_id, due_on)"
                " VALUES (:id, :clinic_id, :patient_id, :visit_id, :due_on)"
            ),
            {
                "id": follow_up_id,
                "clinic_id": clinic_id,
                "patient_id": patient_id,
                "visit_id": visit_id,
                "due_on": due_on,
            },
        )
        return
    if booked_appointment_id is None:
        session.execute(
            text(
                "INSERT INTO follow_up"
                " (id, clinic_id, patient_id, appointment_id, status, due_on)"
                " VALUES (:id, :clinic_id, :patient_id, :visit_id, :status, :due_on)"
            ),
            {
                "id": follow_up_id,
                "clinic_id": clinic_id,
                "patient_id": patient_id,
                "visit_id": visit_id,
                "status": status,
                "due_on": due_on,
            },
        )
        return
    session.execute(
        text(
            "INSERT INTO follow_up"
            " (id, clinic_id, patient_id, appointment_id, status, due_on, booked_appointment_id)"
            " VALUES (:id, :clinic_id, :patient_id, :visit_id, :status, :due_on, :booked)"
        ),
        {
            "id": follow_up_id,
            "clinic_id": clinic_id,
            "patient_id": patient_id,
            "visit_id": visit_id,
            "status": status,
            "due_on": due_on,
            "booked": booked_appointment_id,
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


def _appointment_nullable(database_url: str) -> bool:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT is_nullable FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = 'follow_up'"
            " AND column_name = 'appointment_id'"
        ).fetchone()
    assert row is not None
    return str(row[0]) == "YES"


def _has_index(database_url: str, name: str) -> bool:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT 1 FROM pg_indexes WHERE indexname = %s", (name,)
        ).fetchone()
    return row is not None
