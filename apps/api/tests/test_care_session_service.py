"""Care session rules: visit state, item moves, and one session per visit."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.domain.care_session import SessionFieldError
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_session import CareSession
from dentacircle.services.appointment_service import (
    book_appointment,
    cancel_appointment,
    change_status,
)
from dentacircle.services.care_service import add_item, change_item_status, create_plan
from dentacircle.services.care_session_service import (
    CareSessionView,
    InvalidVisitStatusError,
    ItemChangedError,
    SessionExistsError,
    UnknownItemError,
    get_session,
    record_session,
)
from dentacircle.services.patient_service import register_patient, set_patient_status
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_ZONE = ZoneInfo("Asia/Kolkata")
_DAY = datetime(2026, 10, 17, 9, 0, tzinfo=_ZONE)
_ROLES = ["clinician"]
_NAME = "Sample service"
_TITLE = "Sample plan"
# Written here, not read from the domain table. Removing a pair must fail this test.
_ALLOWED = {
    ("planned", "started"),
    ("planned", "completed"),
    ("started", "completed"),
}
_ITEM_STATUSES = ("planned", "started", "completed", "cancelled")
_VISIT_STATUSES = ("scheduled", "arrived", "in_progress", "completed", "cancelled", "no_show")
_OPENS_A_SESSION = {"arrived", "in_progress"}


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def test_a_session_records_the_items_and_leaves_the_visit_alone(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    visit_id = _visit(clinic_id, actor_id, patient_id, type_id, "arrived", 0)
    first, second = _two_items(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        recorded = record_session(
            session,
            clinic_id,
            actor_id,
            visit_id,
            [(first, "started"), (second, "completed")],
        )
        session.commit()
        session_id = recorded.id
    assert recorded.appointment_id == visit_id
    assert recorded.patient_id == patient_id
    assert recorded.recorded_by_name == "Synthetic Person"
    assert recorded.created_at is not None
    assert [
        (item.care_item_id, item.name, item.plan_title, item.status) for item in recorded.items
    ] == [
        (first, _NAME, _TITLE, "started"),
        (second, _NAME, "Second plan", "completed"),
    ]
    with Session(get_engine()) as session:
        visit = session.get(Appointment, visit_id)
        assert visit is not None
        assert visit.status == "arrived"
        loaded = get_session(session, clinic_id, visit_id)
        assert loaded is not None
        assert loaded.id == session_id
        assert [item.status for item in loaded.items] == ["started", "completed"]


def test_a_bad_list_writes_nothing(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    visit_id = _visit(clinic_id, actor_id, patient_id, type_id, "arrived", 0)
    item_id = _one_item(clinic_id, actor_id, patient_id)
    repeated = item_id
    cases: list[list[tuple[UUID, str]]] = [
        [],
        [(uuid4(), "started")] * 21,
        [(repeated, "started"), (repeated, "completed")],
        [(item_id, "cancelled")],
        [(item_id, "planned")],
    ]
    for entries in cases:
        before = _session_count()
        with Session(get_engine()) as session:
            with pytest.raises(SessionFieldError) as caught:
                record_session(session, clinic_id, actor_id, visit_id, entries)
            assert caught.value.field == "items"
        assert _session_count() == before
        assert _item_status(item_id) == "planned"


def test_every_item_pair(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    slot = 0
    for current in _ITEM_STATUSES:
        for target in _ITEM_STATUSES:
            visit_id = _visit(clinic_id, actor_id, patient_id, type_id, "arrived", slot)
            slot += 1
            item_id = _item_in_status(clinic_id, actor_id, patient_id, current)
            with Session(get_engine()) as session:
                if target not in ("started", "completed"):
                    with pytest.raises(SessionFieldError):
                        record_session(session, clinic_id, actor_id, visit_id, [(item_id, target)])
                elif (current, target) in _ALLOWED:
                    recorded = record_session(
                        session, clinic_id, actor_id, visit_id, [(item_id, target)]
                    )
                    session.commit()
                    assert recorded.items[0].status == target
                else:
                    with pytest.raises(ItemChangedError):
                        record_session(session, clinic_id, actor_id, visit_id, [(item_id, target)])
            if (current, target) not in _ALLOWED or target not in ("started", "completed"):
                assert _item_status(item_id) == current
                assert get_saved(clinic_id, visit_id) is None
            else:
                assert _item_status(item_id) == target


def test_every_visit_status(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    for index, status in enumerate(_VISIT_STATUSES):
        visit_id = _visit(clinic_id, actor_id, patient_id, type_id, status, index)
        item_id = _one_item(clinic_id, actor_id, patient_id, f"Service {index}")
        with Session(get_engine()) as session:
            if status in _OPENS_A_SESSION:
                record_session(session, clinic_id, actor_id, visit_id, [(item_id, "completed")])
                session.commit()
            else:
                with pytest.raises(InvalidVisitStatusError):
                    record_session(session, clinic_id, actor_id, visit_id, [(item_id, "completed")])
        with Session(get_engine()) as session:
            visit = session.get(Appointment, visit_id)
            assert visit is not None
            assert visit.status == status
        if status not in _OPENS_A_SESSION:
            assert _item_status(item_id) == "planned"
            assert get_saved(clinic_id, visit_id) is None


def test_a_second_session_changes_nothing(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    visit_id = _visit(clinic_id, actor_id, patient_id, type_id, "arrived", 0)
    done, missed = _two_items(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        record_session(session, clinic_id, actor_id, visit_id, [(done, "completed")])
        session.commit()
    with Session(get_engine()) as session:
        with pytest.raises(SessionExistsError):
            record_session(session, clinic_id, actor_id, visit_id, [(missed, "started")])
    assert _session_count() == 1
    assert _item_status(done) == "completed"
    assert _item_status(missed) == "planned"


def test_an_item_must_belong_to_this_patient(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    visit_id = _visit(clinic_id, actor_id, patient_id, type_id, "arrived", 0)
    own = _one_item(clinic_id, actor_id, patient_id)
    other_patient = _other_patient_item(clinic_id, actor_id)
    other_clinic = _other_clinic_item()
    for item_id in (uuid4(), other_patient, other_clinic):
        with Session(get_engine()) as session:
            with pytest.raises(UnknownItemError):
                record_session(
                    session,
                    clinic_id,
                    actor_id,
                    visit_id,
                    [(own, "started"), (item_id, "completed")],
                )
        assert _session_count() == 0
        assert _item_status(own) == "planned"


def test_an_inactive_patient_can_still_be_recorded(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    visit_id = _visit(clinic_id, actor_id, patient_id, type_id, "in_progress", 0)
    item_id = _one_item(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        set_patient_status(session, clinic_id, actor_id, patient_id, "inactive")
        session.commit()
    with Session(get_engine()) as session:
        recorded = record_session(session, clinic_id, actor_id, visit_id, [(item_id, "completed")])
        session.commit()
    assert recorded.items[0].status == "completed"
    assert _item_status(item_id) == "completed"


def test_one_refused_item_rolls_the_whole_session_back(database: str) -> None:
    clinic_id, actor_id, patient_id, type_id = _world()
    visit_id = _visit(clinic_id, actor_id, patient_id, type_id, "arrived", 0)
    open_item, finished = _two_items(clinic_id, actor_id, patient_id)
    with Session(get_engine()) as session:
        change_item_status(session, clinic_id, actor_id, finished, "completed")
        session.commit()
    with Session(get_engine()) as session:
        with pytest.raises(ItemChangedError):
            record_session(
                session,
                clinic_id,
                actor_id,
                visit_id,
                [(open_item, "completed"), (finished, "completed")],
            )
    assert _session_count() == 0
    assert _item_status(open_item) == "planned"
    assert _item_status(finished) == "completed"


def get_saved(clinic_id: UUID, visit_id: UUID) -> CareSessionView | None:
    with Session(get_engine()) as session:
        return get_session(session, clinic_id, visit_id)


def _session_count() -> int:
    with Session(get_engine()) as session:
        count = session.scalar(select(func.count()).select_from(CareSession))
    assert count is not None
    return count


def _item_status(item_id: UUID) -> str:
    with Session(get_engine()) as session:
        row = session.get(CareItem, item_id)
        assert row is not None
        return row.status


def _world() -> tuple[UUID, UUID, UUID, UUID]:
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
        consultation = next(
            row
            for row in session.scalars(
                select(AppointmentType).where(AppointmentType.clinic_id == clinic.id)
            )
            if row.name == "Consultation"
        )
        session.commit()
        return clinic.id, actor.id, patient.id, consultation.id


def _visit(
    clinic_id: UUID,
    actor_id: UUID,
    patient_id: UUID,
    type_id: UUID,
    status: str,
    slot: int,
) -> UUID:
    start = _DAY + timedelta(minutes=30 * slot)
    with Session(get_engine()) as session:
        created = book_appointment(
            session,
            clinic_id,
            actor_id,
            patient_id,
            actor_id,
            type_id,
            start,
            start - timedelta(hours=1),
        )
        session.commit()
        visit_id = created.id
    _move_visit(clinic_id, actor_id, visit_id, status, start)
    return visit_id


def _move_visit(
    clinic_id: UUID, actor_id: UUID, visit_id: UUID, status: str, now: datetime
) -> None:
    if status == "scheduled":
        return
    with Session(get_engine()) as session:
        if status == "cancelled":
            cancel_appointment(session, clinic_id, actor_id, visit_id, now)
        elif status == "no_show":
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "no_show", now)
        else:
            change_status(session, clinic_id, actor_id, _ROLES, visit_id, "arrived", now)
            if status in ("in_progress", "completed"):
                change_status(session, clinic_id, actor_id, _ROLES, visit_id, "in_progress", now)
            if status == "completed":
                change_status(session, clinic_id, actor_id, _ROLES, visit_id, "completed", now)
        session.commit()


def _one_item(clinic_id: UUID, actor_id: UUID, patient_id: UUID, name: str = _NAME) -> UUID:
    with Session(get_engine()) as session:
        plan = create_plan(session, clinic_id, actor_id, patient_id, _TITLE)
        item = add_item(session, clinic_id, actor_id, plan.id, name)
        session.commit()
        return item.id


def _two_items(clinic_id: UUID, actor_id: UUID, patient_id: UUID) -> tuple[UUID, UUID]:
    with Session(get_engine()) as session:
        first_plan = create_plan(session, clinic_id, actor_id, patient_id, _TITLE)
        second_plan = create_plan(session, clinic_id, actor_id, patient_id, "Second plan")
        first = add_item(session, clinic_id, actor_id, first_plan.id, _NAME)
        second = add_item(session, clinic_id, actor_id, second_plan.id, _NAME)
        session.commit()
        return first.id, second.id


def _item_in_status(clinic_id: UUID, actor_id: UUID, patient_id: UUID, status: str) -> UUID:
    item_id = _one_item(clinic_id, actor_id, patient_id)
    if status == "planned":
        return item_id
    with Session(get_engine()) as session:
        change_item_status(session, clinic_id, actor_id, item_id, status)
        session.commit()
    return item_id


def _other_patient_item(clinic_id: UUID, actor_id: UUID) -> UUID:
    with Session(get_engine()) as session:
        patient = register_patient(session, clinic_id, actor_id, "Sample Bea", "9000000002", None)
        session.commit()
        patient_id = patient.id
    return _one_item(clinic_id, actor_id, patient_id, "Other service")


def _other_clinic_item() -> UUID:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Other Clinic")
        actor = create_user(
            session,
            clinic.id,
            "b@x.test",
            "Other Person",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, "Sample Cy", "9000000003", None)
        plan = create_plan(session, clinic.id, actor.id, patient.id, "Other plan")
        item = add_item(session, clinic.id, actor.id, plan.id, "Other service")
        session.commit()
        return item.id
