"""Record lab work, move its status, and list it for one patient or the clinic."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.domain.lab_work import (
    STATUS_KIND,
    LabWorkFieldError,
    can_move,
    clean_title,
    expected_on_problem,
    is_overdue,
    statuses_for_view,
)
from dentacircle.domain.patient import display_id
from dentacircle.models.lab_work import LabWork
from dentacircle.models.patient import Patient
from dentacircle.repositories.appointment_repository import AppointmentRepository
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.lab_work_repository import LabWorkRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.audit_service import record
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.follow_up_service import place_follow_up_for_ready_lab
from dentacircle.services.patient_service import PatientNotFoundError
from dentacircle.services.timeline_service import record as record_timeline


class LabWorkNotFoundError(Exception):
    """No such lab item, patient or visit in the caller's clinic."""


class LabWorkPatientInactiveError(Exception):
    """An inactive patient cannot receive new lab work."""


class InvalidLabStatusError(Exception):
    """The lab item cannot take this status."""


@dataclass(frozen=True)
class ActorView:
    id: UUID
    name: str


@dataclass(frozen=True)
class AppointmentLinkView:
    id: UUID
    starts_at: datetime
    type_name: str


@dataclass(frozen=True)
class PatientLinkView:
    id: UUID
    display_id: str
    full_name: str
    phone: str


@dataclass(frozen=True)
class LabWorkView:
    id: UUID
    status: str
    title: str
    expected_on: date | None
    overdue: bool
    appointment: AppointmentLinkView | None
    patient: PatientLinkView
    created_at: datetime
    created_by: ActorView


@dataclass(frozen=True)
class LabWorkPage:
    items: list[LabWorkView]
    total: int
    page: int
    page_size: int


def create_lab_work(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient_id: UUID,
    title: str,
    expected_on: date | None,
    appointment_id: UUID | None,
    now: datetime,
) -> LabWorkView:
    """Validate, then write the row, one create audit event and one timeline step.

    A bad title or date is refused before the patient is looked up. A visit that
    is not this patient's is the same 404 as a missing patient.
    """
    cleaned = clean_title(title)
    zone = _zone(session, clinic_id)
    if expected_on is not None:
        problem = expected_on_problem(expected_on, zone, now)
        if problem is not None:
            raise LabWorkFieldError("expected_on", problem)
    patient = PatientRepository(session, clinic_id).get(patient_id)
    if patient is None:
        raise LabWorkNotFoundError
    if appointment_id is not None:
        visit = AppointmentRepository(session, clinic_id).get_for_patient(
            appointment_id, patient_id
        )
        if visit is None:
            raise LabWorkNotFoundError
    if patient.status != "active":
        raise LabWorkPatientInactiveError
    lab_work = LabWork(
        id=uuid4(),
        patient_id=patient.id,
        appointment_id=appointment_id,
        title=cleaned,
        expected_on=expected_on,
        status="pending",
        created_by_user_id=actor_user_id,
    )
    repository = LabWorkRepository(session, clinic_id)
    repository.add(lab_work)
    record(session, clinic_id, actor_user_id, "lab_work", lab_work.id, "create", changed_fields=[])
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        patient.id,
        "lab_work_created",
        lab_work_id=lab_work.id,
        occurred_at=now,
    )
    session.flush()
    session.refresh(lab_work)
    return _views(session, clinic_id, [(lab_work, patient)], zone, now)[0]


def change_lab_status(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    lab_work_id: UUID,
    status: str,
    now: datetime,
) -> LabWorkView:
    """Lock the patient, then the lab row, then any follow-up a ready move needs."""
    lab_work, patient = _locked(session, clinic_id, lab_work_id)
    if not can_move(lab_work.status, status):
        raise InvalidLabStatusError
    zone = _zone(session, clinic_id)
    if status == "ready":
        place_follow_up_for_ready_lab(
            session,
            clinic_id,
            actor_user_id,
            patient,
            now.astimezone(zone).date(),
            now,
        )
    lab_work.status = status
    record(
        session,
        clinic_id,
        actor_user_id,
        "lab_work",
        lab_work.id,
        "status_change",
        changed_fields=["status"],
    )
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        patient.id,
        STATUS_KIND[status],
        lab_work_id=lab_work.id,
        occurred_at=now,
    )
    session.flush()
    session.refresh(lab_work)
    return _views(session, clinic_id, [(lab_work, patient)], zone, now)[0]


def list_patient_lab_work(
    session: Session,
    clinic_id: UUID,
    patient_id: UUID,
    page: int,
    page_size: int,
    now: datetime,
) -> LabWorkPage:
    """Newest first, every status. An unknown patient is an error. An inactive one is listed."""
    if PatientRepository(session, clinic_id).get(patient_id) is None:
        raise PatientNotFoundError
    zone = _zone(session, clinic_id)
    rows, total = LabWorkRepository(session, clinic_id).list_for_patient(
        patient_id, page, page_size
    )
    return LabWorkPage(
        items=_views(session, clinic_id, rows, zone, now),
        total=total,
        page=page,
        page_size=page_size,
    )


def list_clinic_lab_work(
    session: Session,
    clinic_id: UUID,
    view: str,
    page: int,
    page_size: int,
    now: datetime,
) -> LabWorkPage:
    """Open work first by expected date. Overdue is calculated at read time."""
    zone = _zone(session, clinic_id)
    rows, total = LabWorkRepository(session, clinic_id).list_for_clinic(
        statuses_for_view(view), page, page_size
    )
    return LabWorkPage(
        items=_views(session, clinic_id, rows, zone, now),
        total=total,
        page=page,
        page_size=page_size,
    )


def get_lab_work(
    session: Session, clinic_id: UUID, lab_work_id: UUID, now: datetime
) -> LabWorkView:
    """One lab item in this clinic. Another clinic's id is not found."""
    found = LabWorkRepository(session, clinic_id).get_with_patient(lab_work_id)
    if found is None:
        raise LabWorkNotFoundError
    zone = _zone(session, clinic_id)
    return _views(session, clinic_id, [found], zone, now)[0]


def _locked(session: Session, clinic_id: UUID, lab_work_id: UUID) -> tuple[LabWork, Patient]:
    """Patient row first, then the lab row, so a second ready call sees the first commit.

    The first read is the patient id only, so the session does not cache a stale
    lab row that would hide a concurrent status change.
    """
    patient_id = session.scalar(
        select(LabWork.patient_id).where(LabWork.clinic_id == clinic_id, LabWork.id == lab_work_id)
    )
    if patient_id is None:
        raise LabWorkNotFoundError
    patient = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if patient is None:
        raise RuntimeError("lab work points at a missing patient")
    lab_work = LabWorkRepository(session, clinic_id).get(lab_work_id, lock=True)
    if lab_work is None:
        raise LabWorkNotFoundError
    return lab_work, patient


def _views(
    session: Session,
    clinic_id: UUID,
    rows: list[tuple[LabWork, Patient]],
    zone: ZoneInfo,
    now: datetime,
) -> list[LabWorkView]:
    today = now.astimezone(zone).date()
    repository = LabWorkRepository(session, clinic_id)
    names = repository.creator_names({lab_work.created_by_user_id for lab_work, _patient in rows})
    appointments = repository.appointment_links(
        {
            lab_work.appointment_id
            for lab_work, _patient in rows
            if lab_work.appointment_id is not None
        }
    )
    return [
        _view(lab_work, patient, zone, today, names, appointments) for lab_work, patient in rows
    ]


def _view(
    lab_work: LabWork,
    patient: Patient,
    zone: ZoneInfo,
    today: date,
    names: dict[UUID, str],
    appointments: dict[UUID, tuple[datetime, str]],
) -> LabWorkView:
    name = names.get(lab_work.created_by_user_id)
    if name is None:
        raise RuntimeError("lab work points at a missing user")
    return LabWorkView(
        id=lab_work.id,
        status=lab_work.status,
        title=lab_work.title,
        expected_on=lab_work.expected_on,
        overdue=is_overdue(lab_work.status, lab_work.expected_on, today),
        appointment=_appointment(lab_work, zone, appointments),
        patient=PatientLinkView(
            id=patient.id,
            display_id=display_id(patient.patient_number),
            full_name=patient.full_name,
            phone=patient.phone,
        ),
        created_at=lab_work.created_at.astimezone(zone),
        created_by=ActorView(id=lab_work.created_by_user_id, name=name),
    )


def _appointment(
    lab_work: LabWork,
    zone: ZoneInfo,
    appointments: dict[UUID, tuple[datetime, str]],
) -> AppointmentLinkView | None:
    if lab_work.appointment_id is None:
        return None
    found = appointments.get(lab_work.appointment_id)
    if found is None:
        raise RuntimeError("lab work points at a missing visit")
    starts_at, type_name = found
    return AppointmentLinkView(
        id=lab_work.appointment_id,
        starts_at=starts_at.astimezone(zone),
        type_name=type_name,
    )


def _zone(session: Session, clinic_id: UUID) -> ZoneInfo:
    clinic = ClinicDayRepository(session, clinic_id).get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    try:
        return ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        raise ClinicNotFoundError from None
