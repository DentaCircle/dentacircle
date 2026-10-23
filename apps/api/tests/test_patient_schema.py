"""Patient tables, the number counter, and the audit table."""

import psycopg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import to_psycopg_url
from tests.test_migrations import _config, _public_tables, _version

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_USER = "33333333-3333-3333-3333-333333333333"
_OTHER_USER = "44444444-4444-4444-4444-444444444444"

_HEAD_TABLES = [
    "alembic_version",
    "app_user",
    "appointment",
    "appointment_type",
    "audit_event",
    "auth_session",
    "care_item",
    "care_plan",
    "care_session",
    "care_session_item",
    "clinic",
    "clinic_working_hours",
    "document",
    "follow_up",
    "patient",
    "patient_number_counter",
    "recall",
    "timeline_event",
    "user_role",
]

_PATIENT_COLUMNS = {
    "id",
    "clinic_id",
    "patient_number",
    "full_name",
    "phone",
    "phone_digits",
    "date_of_birth",
    "status",
    "created_at",
}
_COUNTER_COLUMNS = {"clinic_id", "last_number"}
_AUDIT_COLUMNS = {
    "id",
    "clinic_id",
    "actor_user_id",
    "entity_type",
    "entity_id",
    "action",
    "changed_fields",
    "occurred_at",
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
    assert _public_tables(throwaway_database_url) == _HEAD_TABLES
    assert _version(throwaway_database_url) == "0016_document_links"
    assert _columns(throwaway_database_url, "patient") == _PATIENT_COLUMNS
    assert _columns(throwaway_database_url, "patient_number_counter") == _COUNTER_COLUMNS
    assert _columns(throwaway_database_url, "audit_event") == _AUDIT_COLUMNS
    assert "full_name" not in _AUDIT_COLUMNS
    assert "phone" not in _AUDIT_COLUMNS
    assert "date_of_birth" not in _AUDIT_COLUMNS

    command.downgrade(config, "0003_clinic_day")
    tables = _public_tables(throwaway_database_url)
    assert _version(throwaway_database_url) == "0003_clinic_day"
    assert "patient" not in tables
    assert "patient_number_counter" not in tables
    assert "audit_event" not in tables

    command.upgrade(config, "head")
    assert _public_tables(throwaway_database_url) == _HEAD_TABLES
    assert _version(throwaway_database_url) == "0016_document_links"


def test_existing_patients_become_active_and_downgrade_drops_the_columns(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = _config()
    command.upgrade(config, "0004_patients")
    _insert_patient_at_0004(throwaway_database_url)

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0016_document_links"
    nullable, default = _column(throwaway_database_url, "patient", "status")
    assert nullable == "NO"
    assert default is not None and "active" in default
    assert _column(throwaway_database_url, "audit_event", "changed_fields")[0] == "YES"
    assert _patient_status(throwaway_database_url) == "active"
    _reject_unknown_status(throwaway_database_url)

    command.downgrade(config, "0004_patients")
    assert _version(throwaway_database_url) == "0004_patients"
    assert "status" not in _columns(throwaway_database_url, "patient")
    assert "changed_fields" not in _columns(throwaway_database_url, "audit_event")

    command.upgrade(config, "head")
    assert _patient_status(throwaway_database_url) == "active"


def test_patient_number_is_unique_per_clinic(migrated: str, db_session: Session) -> None:
    _insert_clinic(db_session, _CLINIC)
    _insert_clinic(db_session, _OTHER)
    _insert_patient(db_session, _CLINIC, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 1)
    _insert_patient(db_session, _OTHER, "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", 1)
    with pytest.raises(IntegrityError):
        _insert_patient(db_session, _CLINIC, "cccccccc-cccc-cccc-cccc-cccccccccccc", 1)


@pytest.mark.parametrize("digits", ["123456", "1" * 16])
def test_phone_digits_outside_7_to_15_are_rejected(
    migrated: str, db_session: Session, digits: str
) -> None:
    _insert_clinic(db_session, _CLINIC)
    with pytest.raises((IntegrityError, DataError)):
        db_session.execute(
            text(
                "INSERT INTO patient"
                " (id, clinic_id, patient_number, full_name, phone, phone_digits)"
                " VALUES (:id, :clinic_id, 1, 'Sample', :phone, :digits)"
            ),
            {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "clinic_id": _CLINIC,
                "phone": digits,
                "digits": digits,
            },
        )


def test_audit_action_must_be_known_and_the_actor_must_be_in_the_clinic(
    migrated: str, db_session: Session
) -> None:
    _insert_clinic(db_session, _CLINIC)
    _insert_clinic(db_session, _OTHER)
    _insert_user(db_session, _CLINIC, _USER, "a@x.test")
    _insert_user(db_session, _OTHER, _OTHER_USER, "b@x.test")
    _insert_audit(db_session, _CLINIC, _USER, "create", "dddddddd-dddd-dddd-dddd-dddddddddddd")
    with pytest.raises(IntegrityError):
        _insert_audit(db_session, _CLINIC, _USER, "read", "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    db_session.rollback()
    _insert_clinic(db_session, _CLINIC)
    _insert_clinic(db_session, _OTHER)
    _insert_user(db_session, _CLINIC, _USER, "a@x.test")
    _insert_user(db_session, _OTHER, _OTHER_USER, "b@x.test")
    with pytest.raises(IntegrityError):
        _insert_audit(
            db_session, _CLINIC, _OTHER_USER, "create", "dddddddd-dddd-dddd-dddd-dddddddddddd"
        )


def _insert_patient_at_0004(database_url: str) -> None:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        connection.execute(
            "INSERT INTO clinic (id, name) VALUES (%s, 'Synthetic Clinic')",
            (_CLINIC,),
        )
        connection.execute(
            "INSERT INTO patient"
            " (id, clinic_id, patient_number, full_name, phone, phone_digits)"
            " VALUES (%s, %s, 1, 'Sample', '9000000001', '9000000001')",
            ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", _CLINIC),
        )
        connection.commit()


def _column(database_url: str, table: str, column: str) -> tuple[str, str | None]:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT is_nullable, column_default FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
            (table, column),
        ).fetchone()
    assert row is not None
    return (str(row[0]), None if row[1] is None else str(row[1]))


def _patient_status(database_url: str) -> str:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute("SELECT status FROM patient").fetchone()
    assert row is not None
    return str(row[0])


def _reject_unknown_status(database_url: str) -> None:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute("UPDATE patient SET status = 'gone'")


def _columns(database_url: str, table: str) -> set[str]:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def _insert_clinic(session: Session, clinic_id: str) -> None:
    session.execute(
        text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
        {"id": clinic_id},
    )


def _insert_user(session: Session, clinic_id: str, user_id: str, email: str) -> None:
    session.execute(
        text(
            "INSERT INTO app_user (id, clinic_id, email, full_name, password_hash)"
            " VALUES (:id, :clinic_id, :email, 'Synthetic Person', 'hash')"
        ),
        {"id": user_id, "clinic_id": clinic_id, "email": email},
    )


def _insert_patient(session: Session, clinic_id: str, patient_id: str, number: int) -> None:
    session.execute(
        text(
            "INSERT INTO patient"
            " (id, clinic_id, patient_number, full_name, phone, phone_digits)"
            " VALUES (:id, :clinic_id, :number, 'Sample', '9000000001', '9000000001')"
        ),
        {"id": patient_id, "clinic_id": clinic_id, "number": number},
    )


def _insert_audit(
    session: Session, clinic_id: str, user_id: str, action: str, audit_id: str
) -> None:
    session.execute(
        text(
            "INSERT INTO audit_event"
            " (id, clinic_id, actor_user_id, entity_type, entity_id, action)"
            " VALUES (:id, :clinic_id, :user_id, 'patient', :entity_id, :action)"
        ),
        {
            "id": audit_id,
            "clinic_id": clinic_id,
            "user_id": user_id,
            "entity_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "action": action,
        },
    )
