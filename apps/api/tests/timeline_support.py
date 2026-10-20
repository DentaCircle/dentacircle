"""Shared clinic for timeline service tests. Data is synthetic."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine, get_engine
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.timeline_event import TimelineEvent
from dentacircle.services.appointment_service import book_appointment, change_status
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

ZONE = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 12, 8, 0, tzinfo=ZONE)
AT_START = datetime(2026, 10, 12, 10, 0, tzinfo=ZONE)


@dataclass(frozen=True)
class World:
    clinic_id: UUID
    actor_id: UUID
    clinician_id: UUID
    patient_id: UUID
    consultation_id: UUID
    scaling_id: UUID


@pytest.fixture
def database(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    command.upgrade(_config(), "head")
    clear_engine()
    return throwaway_database_url


def world() -> World:
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        actor = create_user(
            session,
            clinic.id,
            "desk@x.test",
            "Sample Desk",
            "synthetic-password-marker",
            ["receptionist", "clinician"],
        )
        clinician = create_user(
            session,
            clinic.id,
            "clinician@x.test",
            "Sample Clinician",
            "synthetic-password-marker",
            ["clinician"],
        )
        patient = register_patient(session, clinic.id, actor.id, "Sample Ada", "9000000001", None)
        types = list(
            session.scalars(select(AppointmentType).where(AppointmentType.clinic_id == clinic.id))
        )
        consultation = next(row for row in types if row.name == "Consultation")
        scaling = next(row for row in types if row.name == "Scaling")
        session.commit()
        return World(clinic.id, actor.id, clinician.id, patient.id, consultation.id, scaling.id)


def kinds(clinic_id: UUID, patient_id: UUID) -> list[str]:
    """Write order: time, then seq."""
    with Session(get_engine()) as session:
        rows = session.scalars(
            select(TimelineEvent)
            .where(
                TimelineEvent.clinic_id == clinic_id,
                TimelineEvent.patient_id == patient_id,
            )
            .order_by(TimelineEvent.occurred_at, TimelineEvent.seq)
        )
        return [row.kind for row in rows]


def book(clinic: World, start: datetime, type_id: UUID | None = None) -> UUID:
    with Session(get_engine()) as session:
        visit = book_appointment(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            clinic.patient_id,
            clinic.clinician_id,
            clinic.consultation_id if type_id is None else type_id,
            start,
            NOW,
        )
        session.commit()
        return visit.id


def move(clinic: World, visit_id: UUID, target: str, now: datetime = NOW) -> None:
    with Session(get_engine()) as session:
        change_status(
            session,
            clinic.clinic_id,
            clinic.actor_id,
            ["clinician"],
            visit_id,
            target,
            now,
        )
        session.commit()


def later(minutes: int) -> datetime:
    return AT_START + timedelta(minutes=minutes)
