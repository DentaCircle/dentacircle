"""Register, read, edit and list one clinic's patients."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from dentacircle.domain.patient import (
    PatientFieldError,
    changed_field_names,
    check_date_of_birth,
    check_status,
    clean_name,
    clean_phone,
    display_id,
    parse_search,
)
from dentacircle.models.patient import Patient
from dentacircle.repositories.clinic_day_repository import ClinicDayRepository
from dentacircle.repositories.patient_repository import PatientRepository
from dentacircle.services.audit_service import record
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.timeline_service import record as record_timeline

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class PatientNotFoundError(Exception):
    """No patient with this id in the caller's clinic."""


@dataclass(frozen=True)
class PatientChanges:
    """Fields present on a PATCH. A missing name means that column stays as it is."""

    fields: frozenset[str]
    full_name: str | None = None
    phone: str | None = None
    date_of_birth: date | None = None


@dataclass(frozen=True)
class PatientView:
    id: UUID
    patient_number: int
    display_id: str
    full_name: str
    phone: str
    date_of_birth: date | None
    status: str
    created_at: datetime


@dataclass(frozen=True)
class PatientPage:
    items: list[PatientView]
    total: int
    page: int
    page_size: int


def register_patient(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    full_name: str,
    phone: str,
    date_of_birth: date | None,
    *,
    occurred_at: datetime | None = None,
) -> PatientView:
    cleaned_name = clean_name(full_name)
    stored_phone, phone_digits = clean_phone(phone)
    check_date_of_birth(date_of_birth, _clinic_today(session, clinic_id))
    repository = PatientRepository(session, clinic_id)
    patient = Patient(
        id=uuid4(),
        patient_number=repository.allocate_number(),
        full_name=cleaned_name,
        phone=stored_phone,
        phone_digits=phone_digits,
        date_of_birth=date_of_birth,
    )
    repository.add(patient)
    record(session, clinic_id, actor_user_id, "patient", patient.id, "create", changed_fields=[])
    moment = occurred_at if occurred_at is not None else datetime.now(UTC)
    record_timeline(
        session,
        clinic_id,
        actor_user_id,
        patient.id,
        "patient_registered",
        occurred_at=moment,
    )
    session.flush()
    session.refresh(patient)
    return _view(patient)


def get_patient(session: Session, clinic_id: UUID, patient_id: UUID) -> PatientView:
    row = PatientRepository(session, clinic_id).get(patient_id)
    if row is None:
        raise PatientNotFoundError
    return _view(row)


def edit_patient(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient_id: UUID,
    changes: PatientChanges,
) -> PatientView:
    row = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if row is None:
        raise PatientNotFoundError
    full_name, phone, phone_digits, date_of_birth = _edited_values(session, clinic_id, row, changes)
    changed = changed_field_names(
        {
            "full_name": row.full_name,
            "phone": row.phone,
            "date_of_birth": row.date_of_birth,
        },
        {"full_name": full_name, "phone": phone, "date_of_birth": date_of_birth},
    )
    if changed:
        row.full_name = full_name
        row.phone = phone
        row.phone_digits = phone_digits
        row.date_of_birth = date_of_birth
        record(
            session,
            clinic_id,
            actor_user_id,
            "patient",
            row.id,
            "update",
            changed_fields=changed,
        )
    session.flush()
    session.refresh(row)
    return _view(row)


def set_patient_status(
    session: Session,
    clinic_id: UUID,
    actor_user_id: UUID,
    patient_id: UUID,
    status: str,
) -> PatientView:
    checked = check_status(status)
    row = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if row is None:
        raise PatientNotFoundError
    changed = changed_field_names({"status": row.status}, {"status": checked})
    if changed:
        row.status = checked
        record(
            session,
            clinic_id,
            actor_user_id,
            "patient",
            row.id,
            "status_change",
            changed_fields=changed,
        )
    session.flush()
    session.refresh(row)
    return _view(row)


def list_patients(
    session: Session,
    clinic_id: UUID,
    query: str | None,
    page: int,
    page_size: int,
    status: str | None = None,
) -> PatientPage:
    if status is not None:
        check_status(status)
    rows, total = PatientRepository(session, clinic_id).search(
        parse_search(query), page, page_size, status=status
    )
    return PatientPage(
        items=[_view(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _edited_values(
    session: Session,
    clinic_id: UUID,
    row: Patient,
    changes: PatientChanges,
) -> tuple[str, str, str, date | None]:
    """Validate every sent field before any column is written."""
    full_name = row.full_name
    phone = row.phone
    phone_digits = row.phone_digits
    date_of_birth = row.date_of_birth
    if "full_name" in changes.fields:
        if changes.full_name is None:
            raise PatientFieldError("full_name", "null_not_allowed")
        full_name = clean_name(changes.full_name)
    if "phone" in changes.fields:
        if changes.phone is None:
            raise PatientFieldError("phone", "null_not_allowed")
        phone, phone_digits = clean_phone(changes.phone)
    if "date_of_birth" in changes.fields:
        check_date_of_birth(changes.date_of_birth, _clinic_today(session, clinic_id))
        date_of_birth = changes.date_of_birth
    return full_name, phone, phone_digits, date_of_birth


def _clinic_today(session: Session, clinic_id: UUID) -> date:
    clinic = ClinicDayRepository(session, clinic_id).get_clinic()
    if clinic is None:
        raise ClinicNotFoundError
    try:
        zone = ZoneInfo(clinic.timezone)
    except ZoneInfoNotFoundError:
        raise ClinicNotFoundError from None
    return datetime.now(zone).date()


def _view(row: Patient) -> PatientView:
    return PatientView(
        id=row.id,
        patient_number=row.patient_number,
        display_id=display_id(row.patient_number),
        full_name=row.full_name,
        phone=row.phone,
        date_of_birth=row.date_of_birth,
        status=row.status,
        created_at=row.created_at,
    )
