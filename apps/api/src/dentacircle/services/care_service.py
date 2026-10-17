"""Create and update one clinic's care plans. Each write records one audit event."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from dentacircle.domain.care import can_move, can_rename, clean_label, is_open
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_plan import CarePlan
from dentacircle.repositories.care_repository import CareRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.audit_service import record


class CareNotFoundError(Exception):
    """No patient, plan or item with this id in the caller's clinic."""


class InvalidStatusError(Exception):
    """The item cannot take this status, or a finished item cannot be renamed."""


class PatientInactiveError(Exception):
    """An inactive patient cannot receive a new plan or item."""


@dataclass(frozen=True)
class CareItemView:
    id: UUID
    name: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class CarePlanView:
    id: UUID
    patient_id: UUID
    title: str
    created_at: datetime
    is_open: bool
    items: list[CareItemView]


def create_plan(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient_id: UUID,
    title: str,
) -> CarePlanView:
    cleaned = clean_label(title, "title")
    _require_active_patient(session, clinic_id, patient_id)
    repository = CareRepository(session, clinic_id)
    plan = CarePlan(id=uuid4(), patient_id=patient_id, title=cleaned)
    repository.add_plan(plan)
    record(session, clinic_id, actor_user_id, "care_plan", plan.id, "create", changed_fields=[])
    session.flush()
    session.refresh(plan)
    return _plan_view(plan, [])


def add_item(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    plan_id: UUID,
    name: str,
) -> CareItemView:
    cleaned = clean_label(name, "name")
    repository = CareRepository(session, clinic_id)
    plan = repository.get_plan(plan_id)
    if plan is None:
        raise CareNotFoundError
    _require_active_patient(session, clinic_id, plan.patient_id)
    item = CareItem(id=uuid4(), care_plan_id=plan.id, name=cleaned, status="planned")
    repository.add_item(item)
    record(session, clinic_id, actor_user_id, "care_item", item.id, "create", changed_fields=[])
    session.flush()
    session.refresh(item)
    return _item_view(item)


def require_patient(session: Session, clinic_id: UUID, patient_id: UUID) -> None:
    """404 when this clinic has no such patient. Does not care if the patient is inactive."""
    if PatientRepository(session, clinic_id).get(patient_id) is None:
        raise CareNotFoundError


def require_plan(session: Session, clinic_id: UUID, plan_id: UUID) -> None:
    if CareRepository(session, clinic_id).get_plan(plan_id) is None:
        raise CareNotFoundError


def require_item(session: Session, clinic_id: UUID, item_id: UUID) -> None:
    if CareRepository(session, clinic_id).get_item(item_id) is None:
        raise CareNotFoundError


def list_plans(session: Session, clinic_id: UUID, patient_id: UUID) -> list[CarePlanView]:
    if PatientRepository(session, clinic_id).get(patient_id) is None:
        raise CareNotFoundError
    repository = CareRepository(session, clinic_id)
    plans = repository.list_plans(patient_id)
    items = repository.list_items([plan.id for plan in plans])
    grouped: dict[UUID, list[CareItem]] = {plan.id: [] for plan in plans}
    for item in items:
        grouped[item.care_plan_id].append(item)
    return [_plan_view(plan, grouped[plan.id]) for plan in plans]


def rename_plan(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    plan_id: UUID,
    title: str,
) -> CarePlanView:
    cleaned = clean_label(title, "title")
    repository = CareRepository(session, clinic_id)
    plan = repository.get_plan(plan_id)
    if plan is None:
        raise CareNotFoundError
    plan.title = cleaned
    record(
        session,
        clinic_id,
        actor_user_id,
        "care_plan",
        plan.id,
        "update",
        changed_fields=["title"],
    )
    session.flush()
    session.refresh(plan)
    items = repository.list_items([plan.id])
    return _plan_view(plan, items)


def rename_item(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    item_id: UUID,
    name: str,
) -> CareItemView:
    cleaned = clean_label(name, "name")
    row = CareRepository(session, clinic_id).get_item_for_update(item_id)
    if row is None:
        raise CareNotFoundError
    if not can_rename(row.status):
        raise InvalidStatusError
    row.name = cleaned
    record(
        session,
        clinic_id,
        actor_user_id,
        "care_item",
        row.id,
        "update",
        changed_fields=["name"],
    )
    session.flush()
    session.refresh(row)
    return _item_view(row)


def change_item_status(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    item_id: UUID,
    target: str,
) -> CareItemView:
    """Lock the item, apply one allowed status move, and write one audit event."""
    row = CareRepository(session, clinic_id).get_item_for_update(item_id)
    if row is None:
        raise CareNotFoundError
    move_locked_item(session, clinic_id, actor_user_id, row, target)
    session.refresh(row)
    return _item_view(row)


def move_locked_item(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    row: CareItem,
    target: str,
) -> None:
    """Apply one allowed move to an item row the caller already locked, and audit it.

    Care sessions call this so the transition table and the status audit exist once.
    """
    if not can_move(row.status, target):
        raise InvalidStatusError
    row.status = target
    record(
        session,
        clinic_id,
        actor_user_id,
        "care_item",
        row.id,
        "status_change",
        changed_fields=["status"],
    )
    session.flush()


def _require_active_patient(session: Session, clinic_id: UUID, patient_id: UUID) -> None:
    patient = PatientRepository(session, clinic_id).get(patient_id)
    if patient is None:
        raise CareNotFoundError
    if patient.status != "active":
        raise PatientInactiveError


def _plan_view(plan: CarePlan, items: list[CareItem]) -> CarePlanView:
    views = [_item_view(item) for item in items]
    return CarePlanView(
        id=plan.id,
        patient_id=plan.patient_id,
        title=plan.title,
        created_at=plan.created_at,
        is_open=is_open([item.status for item in views]),
        items=views,
    )


def _item_view(item: CareItem) -> CareItemView:
    return CareItemView(
        id=item.id,
        name=item.name,
        status=item.status,
        created_at=item.created_at,
    )
