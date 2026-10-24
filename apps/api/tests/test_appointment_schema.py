"""The appointment table, its exclusion rule, and the path back to 0005."""

from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import to_psycopg_url, to_sqlalchemy_url
from tests.test_migrations import _config, _public_tables, _version

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_USER = "33333333-3333-3333-3333-333333333333"
_OTHER_USER = "44444444-4444-4444-4444-444444444444"
_PATIENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_OTHER_PATIENT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_TYPE = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_ZONE = ZoneInfo("UTC")


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 10, 12, hour, minute, tzinfo=_ZONE)


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
    assert _version(throwaway_database_url) == "0017_lab_work"
    assert "appointment" in _public_tables(throwaway_database_url)

    command.downgrade(config, "0005_patient_detail")
    assert _version(throwaway_database_url) == "0005_patient_detail"
    assert "appointment" not in _public_tables(throwaway_database_url)

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0017_lab_work"
    assert "appointment" in _public_tables(throwaway_database_url)


def test_existing_patient_overlaps_stop_the_migration(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = _config()
    command.upgrade(config, "0006_appointments")
    left = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    right = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    engine = create_engine(to_sqlalchemy_url(throwaway_database_url))
    with Session(engine) as session:
        _seed(session)
        _insert(session, left, _USER, _at(10, 0), _at(10, 30))
        _insert(session, right, _OTHER_USER, _at(10, 15), _at(10, 45))
        session.commit()
    engine.dispose()
    with pytest.raises(RuntimeError, match="overlaps") as caught:
        command.upgrade(config, "0007_patient_overlap")
    assert left in str(caught.value)
    assert right in str(caught.value)
    assert _version(throwaway_database_url) == "0006_appointments"
    assert not _has_patient_overlap(throwaway_database_url)


def test_a_cancelled_overlap_does_not_stop_the_migration(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = _config()
    command.upgrade(config, "0006_appointments")
    engine = create_engine(to_sqlalchemy_url(throwaway_database_url))
    with Session(engine) as session:
        _seed(session)
        _insert(session, "dddddddd-dddd-dddd-dddd-dddddddddddd", _USER, _at(10, 0), _at(10, 30))
        _insert(
            session,
            "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
            _OTHER_USER,
            _at(10, 0),
            _at(10, 30),
            status="cancelled",
        )
        session.commit()
    engine.dispose()
    command.upgrade(config, "0007_patient_overlap")
    assert _version(throwaway_database_url) == "0007_patient_overlap"
    assert _has_patient_overlap(throwaway_database_url)


def test_overlapping_blocking_rows_fail_and_the_edges_are_allowed(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert(db_session, "dddddddd-dddd-dddd-dddd-dddddddddddd", _USER, _at(10, 0), _at(10, 30))
    with pytest.raises(IntegrityError) as caught:
        _insert(db_session, "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", _USER, _at(10, 15), _at(10, 45))
    assert getattr(caught.value.orig, "sqlstate", None) == "23P01"


def test_back_to_back_and_two_clinicians_are_allowed(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    _insert(db_session, "dddddddd-dddd-dddd-dddd-dddddddddddd", _USER, _at(10, 0), _at(10, 30))
    _insert(db_session, "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", _USER, _at(10, 30), _at(11, 0))
    _insert(
        db_session,
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        _OTHER_USER,
        _at(10, 0),
        _at(10, 30),
        patient_id=_OTHER_PATIENT,
    )
    db_session.flush()


@pytest.mark.parametrize("status", ["cancelled", "no_show"])
def test_a_non_blocking_row_does_not_occupy_the_clinician(
    migrated: str, db_session: Session, status: str
) -> None:
    _seed(db_session)
    _insert(
        db_session,
        "dddddddd-dddd-dddd-dddd-dddddddddddd",
        _USER,
        _at(10, 0),
        _at(10, 30),
        status=status,
    )
    _insert(db_session, "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", _USER, _at(10, 0), _at(10, 30))
    db_session.flush()


@pytest.mark.parametrize(
    ("start", "end"),
    [(_at(10, 0), _at(10, 0)), (_at(10, 30), _at(10, 0))],
)
def test_a_span_that_does_not_move_forward_is_rejected(
    migrated: str, db_session: Session, start: datetime, end: datetime
) -> None:
    _seed(db_session)
    with pytest.raises(IntegrityError) as caught:
        _insert(db_session, "dddddddd-dddd-dddd-dddd-dddddddddddd", _USER, start, end)
    assert getattr(caught.value.orig, "sqlstate", None) == "23514"


def test_an_unknown_status_is_rejected(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    with pytest.raises(IntegrityError) as caught:
        _insert(
            db_session,
            "dddddddd-dddd-dddd-dddd-dddddddddddd",
            _USER,
            _at(10, 0),
            _at(10, 30),
            status="gone",
        )
    assert getattr(caught.value.orig, "sqlstate", None) == "23514"


def test_one_patient_cannot_overlap_two_clinicians(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    _insert(db_session, "dddddddd-dddd-dddd-dddd-dddddddddddd", _USER, _at(10, 0), _at(10, 30))
    with pytest.raises(IntegrityError) as caught:
        _insert(
            db_session,
            "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
            _OTHER_USER,
            _at(10, 15),
            _at(10, 45),
        )
    diag = getattr(caught.value.orig, "diag", None)
    assert getattr(diag, "constraint_name", None) == "ex_appointment_patient_no_overlap"


def test_one_patient_can_see_two_clinicians_back_to_back(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert(db_session, "dddddddd-dddd-dddd-dddd-dddddddddddd", _USER, _at(10, 0), _at(10, 30))
    _insert(
        db_session, "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", _OTHER_USER, _at(10, 30), _at(11, 0)
    )
    db_session.flush()


def test_a_clinician_from_another_clinic_is_rejected(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    with pytest.raises(IntegrityError):
        _insert(
            db_session,
            "dddddddd-dddd-dddd-dddd-dddddddddddd",
            "55555555-5555-5555-5555-555555555555",
            _at(10, 0),
            _at(10, 30),
        )


def _has_patient_overlap(database_url: str) -> bool:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = 'ex_appointment_patient_no_overlap'"
        ).fetchone()
    return row is not None


def _seed(session: Session) -> None:
    for clinic_id in (_CLINIC, _OTHER):
        session.execute(
            text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
            {"id": clinic_id},
        )
    _user(session, _CLINIC, _USER, "a@x.test")
    _user(session, _CLINIC, _OTHER_USER, "b@x.test")
    _user(session, _OTHER, "55555555-5555-5555-5555-555555555555", "c@x.test")
    _patient(session, _CLINIC, _PATIENT, 1)
    _patient(session, _CLINIC, _OTHER_PATIENT, 2)
    session.execute(
        text(
            "INSERT INTO appointment_type (id, clinic_id, name, duration_minutes)"
            " VALUES (:id, :clinic_id, 'Consultation', 30)"
        ),
        {"id": _TYPE, "clinic_id": _CLINIC},
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


def _insert(
    session: Session,
    appointment_id: str,
    clinician_id: str,
    start: datetime,
    end: datetime,
    status: str = "scheduled",
    patient_id: str = _PATIENT,
) -> None:
    session.execute(
        text(
            "INSERT INTO appointment"
            " (id, clinic_id, patient_id, clinician_user_id, appointment_type_id,"
            "  starts_at, ends_at, status)"
            " VALUES (:id, :clinic_id, :patient_id, :clinician_id, :type_id,"
            "  :starts_at, :ends_at, :status)"
        ),
        {
            "id": appointment_id,
            "clinic_id": _CLINIC,
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "type_id": _TYPE,
            "starts_at": start,
            "ends_at": end,
            "status": status,
        },
    )
