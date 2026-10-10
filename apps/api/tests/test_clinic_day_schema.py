"""The clinic day migration adds columns and tables, and the database enforces the rules."""

from datetime import time

import psycopg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import to_psycopg_url
from dentacircle.domain.clinic_day import (
    DEFAULT_APPOINTMENT_MINUTES,
    DEFAULT_APPOINTMENT_TYPES,
    DEFAULT_TIMEZONE,
    DEFAULT_WORKING_HOURS,
)
from tests.test_migrations import _config, _public_tables, _version

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"

_DAY_TABLES = [
    "alembic_version",
    "app_user",
    "appointment_type",
    "auth_session",
    "clinic",
    "clinic_working_hours",
    "user_role",
]


@pytest.fixture
def migrated(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    return throwaway_database_url


def test_upgrade_downgrade_upgrade_seeds_an_existing_clinic(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = _config()
    command.upgrade(config, "0002_auth")
    _insert_clinic(throwaway_database_url, _CLINIC)

    command.upgrade(config, "0003_clinic_day")
    assert _public_tables(throwaway_database_url) == _DAY_TABLES
    assert _version(throwaway_database_url) == "0003_clinic_day"
    assert _extension_present(throwaway_database_url)
    _assert_defaults(throwaway_database_url, _CLINIC)

    command.downgrade(config, "0002_auth")
    assert _public_tables(throwaway_database_url) == [
        "alembic_version",
        "app_user",
        "auth_session",
        "clinic",
        "user_role",
    ]
    assert _version(throwaway_database_url) == "0002_auth"
    assert "timezone" not in _clinic_columns(throwaway_database_url)
    assert _extension_present(throwaway_database_url)
    assert not _timerange_present(throwaway_database_url)

    command.upgrade(config, "0003_clinic_day")
    assert _version(throwaway_database_url) == "0003_clinic_day"
    _assert_defaults(throwaway_database_url, _CLINIC)


def test_new_clinic_columns_default_when_omitted(migrated: str, db_session: Session) -> None:
    db_session.execute(
        text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
        {"id": _CLINIC},
    )
    row = db_session.execute(
        text("SELECT timezone, default_appointment_minutes FROM clinic WHERE id = :id"),
        {"id": _CLINIC},
    ).one()
    assert row.timezone == "Asia/Kolkata"
    assert row.default_appointment_minutes == 30


@pytest.mark.parametrize("minutes", [4, 481])
def test_default_duration_outside_5_to_480_is_rejected(
    migrated: str, db_session: Session, minutes: int
) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE clinic SET default_appointment_minutes = :minutes WHERE id = :id"),
            {"minutes": minutes, "id": _CLINIC},
        )


def test_edges_of_the_duration_range_are_stored(migrated: str, db_session: Session) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    for minutes in (5, 480):
        db_session.execute(
            text("UPDATE clinic SET default_appointment_minutes = :minutes WHERE id = :id"),
            {"minutes": minutes, "id": _CLINIC},
        )
    stored: int = db_session.execute(
        text("SELECT default_appointment_minutes FROM clinic WHERE id = :id"),
        {"id": _CLINIC},
    ).scalar_one()
    assert stored == 480


@pytest.mark.parametrize("weekday", [-1, 7])
def test_weekday_outside_0_to_6_is_rejected(
    migrated: str, db_session: Session, weekday: int
) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    with pytest.raises(IntegrityError):
        _insert_hours(db_session, _CLINIC, weekday, time(9, 0), time(12, 0))


@pytest.mark.parametrize(
    ("opens_at", "closes_at"),
    [(time(12, 0), time(12, 0)), (time(13, 0), time(12, 0))],
)
def test_opens_at_must_be_before_closes_at(
    migrated: str, db_session: Session, opens_at: time, closes_at: time
) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    with pytest.raises(IntegrityError):
        _insert_hours(db_session, _CLINIC, 0, opens_at, closes_at)


def test_overlapping_intervals_on_one_weekday_are_rejected(
    migrated: str, db_session: Session
) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    _insert_hours(db_session, _CLINIC, 0, time(9, 0), time(13, 0))
    with pytest.raises(IntegrityError):
        _insert_hours(db_session, _CLINIC, 0, time(12, 0), time(18, 0))


def test_touching_intervals_on_one_weekday_are_rejected(migrated: str, db_session: Session) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    _insert_hours(db_session, _CLINIC, 0, time(9, 0), time(12, 0))
    with pytest.raises(IntegrityError):
        _insert_hours(db_session, _CLINIC, 0, time(12, 0), time(18, 0))


def test_a_gap_between_intervals_is_a_break(migrated: str, db_session: Session) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    _insert_hours(db_session, _CLINIC, 0, time(9, 0), time(12, 0))
    _insert_hours(db_session, _CLINIC, 0, time(13, 0), time(18, 0))
    count: int = db_session.execute(
        text("SELECT count(*) FROM clinic_working_hours WHERE clinic_id = :id"),
        {"id": _CLINIC},
    ).scalar_one()
    assert count == 2


def test_the_same_interval_is_allowed_on_another_weekday_and_clinic(
    migrated: str, db_session: Session
) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    _insert_clinic_row(db_session, _OTHER)
    _insert_hours(db_session, _CLINIC, 0, time(9, 0), time(12, 0))
    _insert_hours(db_session, _CLINIC, 1, time(9, 0), time(12, 0))
    _insert_hours(db_session, _OTHER, 0, time(9, 0), time(12, 0))


def test_type_duration_may_be_empty_or_on_the_boundary(migrated: str, db_session: Session) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    _insert_type(db_session, _CLINIC, "33333333-3333-3333-3333-333333333333", "Polish", None)
    _insert_type(db_session, _CLINIC, "44444444-4444-4444-4444-444444444444", "Review", 5)
    _insert_type(db_session, _CLINIC, "55555555-5555-5555-5555-555555555555", "Long visit", 480)


@pytest.mark.parametrize("minutes", [4, 481])
def test_type_duration_outside_5_to_480_is_rejected(
    migrated: str, db_session: Session, minutes: int
) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    with pytest.raises(IntegrityError):
        _insert_type(
            db_session,
            _CLINIC,
            "55555555-5555-5555-5555-555555555555",
            "Bad duration",
            minutes,
        )


def test_type_names_are_unique_per_clinic_ignoring_case(migrated: str, db_session: Session) -> None:
    _insert_clinic_row(db_session, _CLINIC)
    _insert_clinic_row(db_session, _OTHER)
    _insert_type(db_session, _CLINIC, "33333333-3333-3333-3333-333333333333", "Scaling", 30)
    _insert_type(db_session, _OTHER, "44444444-4444-4444-4444-444444444444", "Scaling", 30)
    with pytest.raises(IntegrityError):
        _insert_type(db_session, _CLINIC, "55555555-5555-5555-5555-555555555555", "scaling", 30)


def _assert_defaults(database_url: str, clinic_id: str) -> None:
    with psycopg.connect(to_psycopg_url(database_url)) as connection:
        clinic = connection.execute(
            "SELECT timezone, default_appointment_minutes FROM clinic WHERE id = %s",
            (clinic_id,),
        ).fetchone()
        hours = connection.execute(
            "SELECT weekday, opens_at, closes_at FROM clinic_working_hours"
            " WHERE clinic_id = %s ORDER BY weekday, opens_at",
            (clinic_id,),
        ).fetchall()
        types = connection.execute(
            "SELECT name, duration_minutes, is_active FROM appointment_type"
            " WHERE clinic_id = %s ORDER BY name",
            (clinic_id,),
        ).fetchall()
    assert clinic == (DEFAULT_TIMEZONE, DEFAULT_APPOINTMENT_MINUTES)
    assert [(row[0], row[1], row[2]) for row in hours] == [
        (item.weekday, item.opens_at, item.closes_at) for item in DEFAULT_WORKING_HOURS
    ]
    assert [(row[0], row[1], row[2]) for row in types] == [
        (item.name, item.duration_minutes, True)
        for item in sorted(DEFAULT_APPOINTMENT_TYPES, key=lambda item: item.name)
    ]
    assert DEFAULT_TIMEZONE == "Asia/Kolkata"
    assert DEFAULT_APPOINTMENT_MINUTES == 30
    assert [item.weekday for item in DEFAULT_WORKING_HOURS] == [0, 1, 2, 3, 4, 5]
    assert [(item.name, item.duration_minutes) for item in DEFAULT_APPOINTMENT_TYPES] == [
        ("Consultation", 30),
        ("Scaling", 30),
        ("Root canal visit", 60),
        ("Crown visit", 45),
    ]


def _insert_clinic(database_url: str, clinic_id: str) -> None:
    with psycopg.connect(to_psycopg_url(database_url)) as connection:
        connection.execute(
            "INSERT INTO clinic (id, name) VALUES (%s, 'Synthetic Clinic')",
            (clinic_id,),
        )
        connection.commit()


def _insert_clinic_row(session: Session, clinic_id: str) -> None:
    session.execute(
        text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
        {"id": clinic_id},
    )


def _insert_hours(
    session: Session, clinic_id: str, weekday: int, opens_at: time, closes_at: time
) -> None:
    session.execute(
        text(
            "INSERT INTO clinic_working_hours (clinic_id, weekday, opens_at, closes_at)"
            " VALUES (:clinic, :weekday, :opens_at, :closes_at)"
        ),
        {
            "clinic": clinic_id,
            "weekday": weekday,
            "opens_at": opens_at,
            "closes_at": closes_at,
        },
    )


def _insert_type(
    session: Session, clinic_id: str, type_id: str, name: str, duration: int | None
) -> None:
    session.execute(
        text(
            "INSERT INTO appointment_type (id, clinic_id, name, duration_minutes, is_active)"
            " VALUES (:id, :clinic, :name, :duration, true)"
        ),
        {"id": type_id, "clinic": clinic_id, "name": name, "duration": duration},
    )


def _clinic_columns(database_url: str) -> set[str]:
    with psycopg.connect(to_psycopg_url(database_url)) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'clinic'"
        ).fetchall()
    return {row[0] for row in rows}


def _extension_present(database_url: str) -> bool:
    with psycopg.connect(to_psycopg_url(database_url)) as connection:
        row = connection.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'"
        ).fetchone()
    return row is not None


def _timerange_present(database_url: str) -> bool:
    with psycopg.connect(to_psycopg_url(database_url)) as connection:
        row = connection.execute("SELECT 1 FROM pg_type WHERE typname = 'timerange'").fetchone()
    return row is not None
