"""Care plan rules: names, open or finished, status moves, and inactive patients."""

from uuid import UUID

import pytest
from alembic import command
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.care import CareFieldError
from dentacircle.services.care_service import (
    CareNotFoundError,
    InvalidStatusError,
    PatientInactiveError,
    add_item,
    change_item_status,
    create_plan,
    list_plans,
    rename_item,
    rename_plan,
)
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_TITLE = "Sample plan"
_NAME = "Sample service"
# Written here, not read from the domain table. Removing a pair must fail this test.
_ALLOWED = {
    ("planned", "started"),
    ("planned", "completed"),
    ("planned", "cancelled"),
    ("started", "completed"),
    ("started", "cancelled"),
}
_STATUSES = ("planned", "started", "completed", "cancelled")


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_a_new_plan_is_trimmed_and_not_open(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    with Session(get_engine()) as session:
        created = create_plan(session, clinic_id, actor_id, patient_id, f"  {_TITLE}  ")
        session.commit()
    assert created.title == _TITLE
    assert created.patient_id == patient_id
    assert created.is_open is False
    assert created.items == []
    assert created.created_at is not None


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_a_blank_or_long_title_is_refused(database: str, title: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    with Session(get_engine()) as session:
        with pytest.raises(CareFieldError) as caught:
            create_plan(session, clinic_id, actor_id, patient_id, title)
        assert caught.value.field == "title"
    with Session(get_engine()) as session:
        assert list_plans(session, clinic_id, patient_id) == []


def test_an_item_starts_planned_and_duplicate_names_are_kept(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    plan_id = _plan(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        first = add_item(session, clinic_id, actor_id, plan_id, f"  {_NAME}  ")
        second = add_item(session, clinic_id, actor_id, plan_id, _NAME)
        session.commit()
    assert first.name == _NAME
    assert first.status == "planned"
    assert second.name == _NAME
    assert first.id != second.id


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_a_blank_or_long_item_name_is_refused(database: str, name: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    plan_id = _plan(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        with pytest.raises(CareFieldError) as caught:
            add_item(session, clinic_id, actor_id, plan_id, name)
        assert caught.value.field == "name"
        plans = list_plans(session, clinic_id, patient_id)
    assert plans[0].items == []


def test_plans_are_newest_first_and_open_follows_the_items(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    with Session(get_engine()) as session:
        older = create_plan(session, clinic_id, actor_id, patient_id, "Older")
        session.commit()
        older_id = older.id
    with Session(get_engine()) as session:
        newer = create_plan(session, clinic_id, actor_id, patient_id, "Newer")
        session.commit()
        newer_id = newer.id
    with Session(get_engine()) as session:
        first = add_item(session, clinic_id, actor_id, newer_id, "First")
        session.commit()
        first_id = first.id
    with Session(get_engine()) as session:
        second = add_item(session, clinic_id, actor_id, newer_id, "Second")
        session.commit()
        second_id = second.id
    with Session(get_engine()) as session:
        change_item_status(session, clinic_id, actor_id, second_id, "completed")
        session.commit()
    with Session(get_engine()) as session:
        finished_item = add_item(session, clinic_id, actor_id, older_id, "Done")
        change_item_status(session, clinic_id, actor_id, finished_item.id, "cancelled")
        session.commit()
    with Session(get_engine()) as session:
        plans = list_plans(session, clinic_id, patient_id)
    assert [plan.id for plan in plans] == [newer_id, older_id]
    assert [item.name for item in plans[0].items] == ["First", "Second"]
    assert plans[0].is_open is True
    assert plans[1].is_open is False
    with Session(get_engine()) as session:
        change_item_status(session, clinic_id, actor_id, first_id, "completed")
        session.commit()
        plans = list_plans(session, clinic_id, patient_id)
    assert plans[0].is_open is False


def test_a_patient_with_no_plans_returns_an_empty_list(database: str) -> None:
    clinic_id, _actor_id, patient_id = _world()
    with Session(get_engine()) as session:
        assert list_plans(session, clinic_id, patient_id) == []


def test_a_missing_patient_plan_or_item_is_not_found(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    missing = UUID("99999999-9999-9999-9999-999999999999")
    with Session(get_engine()) as session:
        with pytest.raises(CareNotFoundError):
            list_plans(session, clinic_id, missing)
        with pytest.raises(CareNotFoundError):
            create_plan(session, clinic_id, actor_id, missing, _TITLE)
        with pytest.raises(CareNotFoundError):
            add_item(session, clinic_id, actor_id, missing, _NAME)
        with pytest.raises(CareNotFoundError):
            rename_plan(session, clinic_id, actor_id, missing, "Other")
        with pytest.raises(CareNotFoundError):
            rename_item(session, clinic_id, actor_id, missing, "Other")
        with pytest.raises(CareNotFoundError):
            change_item_status(session, clinic_id, actor_id, missing, "started")
        assert list_plans(session, clinic_id, patient_id) == []


def test_a_plan_and_an_open_item_can_be_renamed(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    plan_id, item_id = _plan_and_item(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        plan = rename_plan(session, clinic_id, actor_id, plan_id, "  Renamed plan  ")
        item = rename_item(session, clinic_id, actor_id, item_id, "  Renamed service  ")
        session.commit()
    assert plan.title == "Renamed plan"
    assert plan.items[0].name == _NAME
    assert item.name == "Renamed service"
    with Session(get_engine()) as session:
        change_item_status(session, clinic_id, actor_id, item_id, "started")
        renamed = rename_item(session, clinic_id, actor_id, item_id, "Still open")
        session.commit()
    assert renamed.name == "Still open"
    assert renamed.status == "started"


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_a_finished_item_cannot_be_renamed(database: str, status: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    _plan_id, item_id = _plan_and_item(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        change_item_status(session, clinic_id, actor_id, item_id, status)
        session.commit()
    with Session(get_engine()) as session:
        with pytest.raises(InvalidStatusError):
            rename_item(session, clinic_id, actor_id, item_id, "Changed")
        plans = list_plans(session, clinic_id, patient_id)
    assert plans[0].items[0].name == _NAME
    assert plans[0].items[0].status == status


def test_every_status_pair(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    for current in _STATUSES:
        for target in _STATUSES:
            item_id = _item_at(clinic_id, actor_id, patient_id, current)
            with Session(get_engine()) as session:
                if (current, target) in _ALLOWED:
                    moved = change_item_status(session, clinic_id, actor_id, item_id, target)
                    session.commit()
                    assert moved.status == target
                else:
                    with pytest.raises(InvalidStatusError):
                        change_item_status(session, clinic_id, actor_id, item_id, target)
                    plans = list_plans(session, clinic_id, patient_id)
                    found = next(
                        item for plan in plans for item in plan.items if item.id == item_id
                    )
                    assert found.status == current


def test_an_inactive_patient_gets_no_new_care_but_open_items_can_finish(database: str) -> None:
    clinic_id, actor_id, patient_id = _world()
    plan_id, item_id = _plan_and_item(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
    with Session(get_engine()) as session:
        with pytest.raises(PatientInactiveError):
            create_plan(session, clinic_id, actor_id, patient_id, "Another")
        with pytest.raises(PatientInactiveError):
            add_item(session, clinic_id, actor_id, plan_id, "Another")
        plans = list_plans(session, clinic_id, patient_id)
        assert len(plans) == 1
        renamed = rename_item(session, clinic_id, actor_id, item_id, "Wrap up")
        moved = change_item_status(session, clinic_id, actor_id, item_id, "completed")
        session.commit()
    assert renamed.name == "Wrap up"
    assert moved.status == "completed"


def _world() -> tuple[UUID, UUID, UUID]:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "a@x.test",
            "Synthetic Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, "Sample Ada", "9000000001", None)
        session.commit()
        return clinic.id, actor.id, patient.id


def _plan(clinic_id: UUID, actor_id: UUID, patient_id: UUID) -> UUID:
    with Session(get_engine()) as session:
        created = create_plan(session, clinic_id, actor_id, patient_id, _TITLE)
        session.commit()
        return created.id


def _plan_and_item(clinic_id: UUID, actor_id: UUID, patient_id: UUID) -> tuple[UUID, UUID]:
    plan_id = _plan(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        item = add_item(session, clinic_id, actor_id, plan_id, _NAME)
        session.commit()
        return plan_id, item.id


def _item_at(clinic_id: UUID, actor_id: UUID, patient_id: UUID, status: str) -> UUID:
    _plan_id, item_id = _plan_and_item(clinic_id, actor_id, patient_id)
    if status == "planned":
        return item_id
    with Session(get_engine()) as session:
        if status == "started":
            change_item_status(session, clinic_id, actor_id, item_id, "started")
        else:
            change_item_status(session, clinic_id, actor_id, item_id, status)
        session.commit()
    return item_id
