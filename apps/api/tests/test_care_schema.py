"""Care plan and care item tables, checks, and composite foreign keys."""

import psycopg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dentacircle.core.database import to_psycopg_url
from tests.test_migrations import _config, _public_tables, _version

_CLINIC = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_PATIENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_OTHER_PATIENT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_PLAN = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_ITEM = "dddddddd-dddd-dddd-dddd-dddddddddddd"


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
    assert _version(throwaway_database_url) == "0008_care_plans"
    assert "care_plan" in _public_tables(throwaway_database_url)
    assert "care_item" in _public_tables(throwaway_database_url)
    assert _columns(throwaway_database_url, "care_plan") == {
        "id",
        "clinic_id",
        "patient_id",
        "title",
        "created_at",
    }
    assert _columns(throwaway_database_url, "care_item") == {
        "id",
        "clinic_id",
        "care_plan_id",
        "name",
        "status",
        "created_at",
    }

    command.downgrade(config, "0007_patient_overlap")
    tables = _public_tables(throwaway_database_url)
    assert _version(throwaway_database_url) == "0007_patient_overlap"
    assert "care_plan" not in tables
    assert "care_item" not in tables

    command.upgrade(config, "head")
    assert _version(throwaway_database_url) == "0008_care_plans"
    assert "care_plan" in _public_tables(throwaway_database_url)
    assert "care_item" in _public_tables(throwaway_database_url)


def test_status_must_be_one_of_four_and_defaults_to_planned(
    migrated: str, db_session: Session
) -> None:
    _seed(db_session)
    _insert_plan(db_session, _CLINIC, _PATIENT, _PLAN)
    _insert_item(db_session, _CLINIC, _PLAN, _ITEM, status=None)
    status: str = db_session.execute(
        text("SELECT status FROM care_item WHERE id = :id"), {"id": _ITEM}
    ).scalar_one()
    assert status == "planned"
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_item(
            db_session,
            _CLINIC,
            _PLAN,
            "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
            status="done",
        )


def test_a_plan_cannot_point_at_another_clinics_patient(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    with pytest.raises(IntegrityError):
        _insert_plan(db_session, _OTHER, _PATIENT, _PLAN)


def test_an_item_cannot_point_at_another_clinics_plan(migrated: str, db_session: Session) -> None:
    _seed(db_session)
    _insert_plan(db_session, _CLINIC, _PATIENT, _PLAN)
    db_session.commit()
    with pytest.raises(IntegrityError):
        _insert_item(db_session, _OTHER, _PLAN, _ITEM, status="planned")


def _seed(session: Session) -> None:
    for clinic_id in (_CLINIC, _OTHER):
        session.execute(
            text("INSERT INTO clinic (id, name) VALUES (:id, 'Synthetic Clinic')"),
            {"id": clinic_id},
        )
    for clinic_id, patient_id, number in (
        (_CLINIC, _PATIENT, 1),
        (_OTHER, _OTHER_PATIENT, 1),
    ):
        session.execute(
            text(
                "INSERT INTO patient"
                " (id, clinic_id, patient_number, full_name, phone, phone_digits)"
                " VALUES (:id, :clinic_id, :number, 'Sample', '9000000001', '9000000001')"
            ),
            {"id": patient_id, "clinic_id": clinic_id, "number": number},
        )


def _insert_plan(session: Session, clinic_id: str, patient_id: str, plan_id: str) -> None:
    session.execute(
        text(
            "INSERT INTO care_plan (id, clinic_id, patient_id, title)"
            " VALUES (:id, :clinic_id, :patient_id, 'Sample plan')"
        ),
        {"id": plan_id, "clinic_id": clinic_id, "patient_id": patient_id},
    )


def _insert_item(
    session: Session, clinic_id: str, plan_id: str, item_id: str, status: str | None
) -> None:
    if status is None:
        session.execute(
            text(
                "INSERT INTO care_item (id, clinic_id, care_plan_id, name)"
                " VALUES (:id, :clinic_id, :plan_id, 'Sample service')"
            ),
            {"id": item_id, "clinic_id": clinic_id, "plan_id": plan_id},
        )
        return
    session.execute(
        text(
            "INSERT INTO care_item (id, clinic_id, care_plan_id, name, status)"
            " VALUES (:id, :clinic_id, :plan_id, 'Sample service', :status)"
        ),
        {"id": item_id, "clinic_id": clinic_id, "plan_id": plan_id, "status": status},
    )


def _columns(database_url: str, table: str) -> set[str]:
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}
