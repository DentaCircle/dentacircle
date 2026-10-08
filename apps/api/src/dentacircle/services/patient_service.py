"""Register a patient and list the clinic's patients."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from dentacircle.domain.patient import (
    check_date_of_birth,
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

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class PatientView:
    id: UUID
    patient_number: int
    display_id: str
    full_name: str
    phone: str
    date_of_birth: date | None
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
    record(session, clinic_id, actor_user_id, "patient", patient.id, "create")
    session.flush()
    session.refresh(patient)
    return _view(patient)


def list_patients(
    session: Session,
    clinic_id: UUID,
    query: str | None,
    page: int,
    page_size: int,
) -> PatientPage:
    rows, total = PatientRepository(session, clinic_id).search(parse_search(query), page, page_size)
    return PatientPage(
        items=[_view(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


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
        created_at=row.created_at,
    )
