"""Create an isolated synthetic clinic for S5.2b's local review."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from alembic import command
from dentacircle.core.database import clear_engine, get_engine
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.services.appointment_service import book_appointment
from dentacircle.services.patient_service import register_patient
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.support import create_throwaway_database
from tests.test_migrations import _config


def main() -> None:
    database = create_throwaway_database(
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle"
    )
    os.environ["DATABASE_URL"] = database
    command.upgrade(_config(), "head")
    clear_engine()
    with Session(get_engine(), expire_on_commit=False) as session:
        clinic = get_or_create_clinic(session, "Synthetic Demo Clinic")
        staff = create_user(
            session,
            clinic.id,
            "proof@example.test",
            "Synthetic Staff",
            "synthetic-proof-password",
            ["clinic_admin", "clinician", "receptionist"],
        )
        patient = register_patient(
            session, clinic.id, staff.id, "Synthetic Patient", "9000000001", None
        )
        appointment_type = session.scalar(
            select(AppointmentType)
            .where(
                AppointmentType.clinic_id == clinic.id,
                AppointmentType.is_active.is_(True),
            )
            .limit(1)
        )
        assert appointment_type is not None
        now = datetime.now(UTC)
        zone = ZoneInfo(clinic.timezone)
        day = now.astimezone(zone).date() + timedelta(days=1)
        while day.weekday() == 6:
            day += timedelta(days=1)
        start = datetime(day.year, day.month, day.day, 10, 0, tzinfo=zone)
        book_appointment(
            session,
            clinic.id,
            staff.id,
            patient.id,
            staff.id,
            appointment_type.id,
            start,
            now,
        )
        session.commit()
        details = {
            "database_url": database,
            "clinic_id": str(clinic.id),
            "patient_id": str(patient.id),
            "staff_id": str(staff.id),
        }
    path = Path("../../.openwa/proof.json")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(details))
    path.chmod(0o600)
    print("Synthetic proof clinic is ready.")


if __name__ == "__main__":
    main()
