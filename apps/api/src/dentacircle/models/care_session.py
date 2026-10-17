"""One care session for one visit. There is no second session and no edit."""

from uuid import UUID

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.models.mixins import ClinicScoped


class CareSession(ClinicScoped, Base):
    __tablename__ = "care_session"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id", name="uq_care_session_id_clinic_id"),
        UniqueConstraint("clinic_id", "appointment_id", name="uq_care_session_clinic_appointment"),
        ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointment.id", "appointment.clinic_id"],
            name="fk_care_session_appointment_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_care_session_patient_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "recorded_by_user_id"],
            ["app_user.clinic_id", "app_user.id"],
            name="fk_care_session_recorded_by_user_id",
        ),
        Index("ix_care_session_clinic_patient_created", "clinic_id", "patient_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    appointment_id: Mapped[UUID] = mapped_column()
    patient_id: Mapped[UUID] = mapped_column()
    recorded_by_user_id: Mapped[UUID] = mapped_column()
