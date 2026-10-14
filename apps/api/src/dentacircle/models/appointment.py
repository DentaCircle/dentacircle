"""One visit. A clinician cannot have two blocking visits at the same time."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import literal_column

from dentacircle.core.database import Base
from dentacircle.domain.appointment import APPOINTMENT_STATUSES, SCHEDULED
from dentacircle.models.mixins import ClinicScoped

_STATUSES = ", ".join(f"'{status}'" for status in APPOINTMENT_STATUSES)


class Appointment(ClinicScoped, Base):
    __tablename__ = "appointment"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_known"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_appointment_patient_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_type.id", "appointment_type.clinic_id"],
            name="fk_appointment_type_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "clinician_user_id"],
            ["app_user.clinic_id", "app_user.id"],
            name="fk_appointment_clinician_user_id",
        ),
        Index("ix_appointment_clinic_patient_starts", "clinic_id", "patient_id", "starts_at"),
        Index("ix_appointment_clinic_starts", "clinic_id", "starts_at"),
        ExcludeConstraint(
            ("clinic_id", "="),
            ("clinician_user_id", "="),
            (literal_column("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            where=text("status NOT IN ('cancelled', 'no_show')"),
            using="gist",
            name="ex_appointment_no_overlap",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    patient_id: Mapped[UUID] = mapped_column()
    clinician_user_id: Mapped[UUID] = mapped_column()
    appointment_type_id: Mapped[UUID] = mapped_column()
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        Text, default=SCHEDULED, server_default=text(f"'{SCHEDULED}'")
    )
