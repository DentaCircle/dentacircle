"""Effective duration follows the type, then the clinic default."""

from datetime import time

import pytest
from alembic import command
from sqlalchemy.orm import Session

from dentacircle.domain.clinic_day import ClinicDayValidationError
from dentacircle.services.appointment_type_service import (
    ConflictError,
    create_appointment_type,
    effective_duration_minutes,
    list_appointment_types,
    update_appointment_type,
)
from dentacircle.services.clinic_day_service import (
    read_clinic_day,
    replace_clinic_day,
)
from dentacircle.services.provisioning_service import get_or_create_clinic
from tests.test_migrations import _config


@pytest.fixture
def migrated(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")


def test_effective_duration_uses_the_type_then_the_clinic_default(
    migrated: None, db_session: Session
) -> None:
    assert effective_duration_minutes(None, 30) == 30
    assert effective_duration_minutes(60, 30) == 60

    clinic = get_or_create_clinic(db_session, "Synthetic Clinic")
    created = create_appointment_type(db_session, clinic.id, "  Polish  ", None)
    assert created.name == "Polish"
    assert created.duration_minutes is None
    assert created.effective_duration_minutes == 30

    replace_clinic_day(
        db_session,
        clinic.id,
        "Asia/Kolkata",
        20,
        _weekday_hours(),
    )
    listed = list_appointment_types(db_session, clinic.id, include_inactive=False)
    by_name = {item.name: item for item in listed}
    assert by_name["Polish"].effective_duration_minutes == 20
    assert by_name["Root canal visit"].duration_minutes == 60
    assert by_name["Root canal visit"].effective_duration_minutes == 60


def test_a_duplicate_name_is_rejected_and_deactivating_keeps_the_row(
    migrated: None, db_session: Session
) -> None:
    clinic = get_or_create_clinic(db_session, "Synthetic Clinic")
    with pytest.raises(ConflictError):
        create_appointment_type(db_session, clinic.id, "scaling", 30)
    scaling = next(
        item
        for item in list_appointment_types(db_session, clinic.id, include_inactive=False)
        if item.name == "Scaling"
    )
    updated = update_appointment_type(
        db_session, clinic.id, scaling.id, "Scaling", 30, is_active=False
    )
    assert updated.is_active is False
    names = [
        item.name for item in list_appointment_types(db_session, clinic.id, include_inactive=False)
    ]
    assert "Scaling" not in names
    inactive = list_appointment_types(db_session, clinic.id, include_inactive=True)
    assert any(item.name == "Scaling" and item.is_active is False for item in inactive)


def test_replace_rejects_a_bad_timezone_and_touching_intervals(
    migrated: None, db_session: Session
) -> None:
    clinic = get_or_create_clinic(db_session, "Synthetic Clinic")
    before = read_clinic_day(db_session, clinic.id)
    with pytest.raises(ClinicDayValidationError) as unknown:
        replace_clinic_day(db_session, clinic.id, "Not/AZone", 30, [(0, time(9, 0), time(17, 0))])
    assert unknown.value.code == "unknown_timezone"
    with pytest.raises(ClinicDayValidationError) as touching:
        replace_clinic_day(
            db_session,
            clinic.id,
            "Asia/Kolkata",
            30,
            [(0, time(9, 0), time(12, 0)), (0, time(12, 0), time(18, 0))],
        )
    assert touching.value.code == "interval_overlap"
    assert read_clinic_day(db_session, clinic.id) == before


def _weekday_hours() -> list[tuple[int, time, time]]:
    return [(weekday, time(9, 0), time(18, 0)) for weekday in range(6)]
