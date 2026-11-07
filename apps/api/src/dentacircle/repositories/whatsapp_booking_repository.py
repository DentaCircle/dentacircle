"""Clinic-scoped reads used by the patient booking dialogue."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.follow_up import FollowUp
from dentacircle.models.recall import Recall
from dentacircle.models.user_role import UserRole


class WhatsAppBookingRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self.session = session
        self.clinic_id = clinic_id

    def sources(self, patient_id: UUID) -> list[tuple[str, UUID, str]]:
        follow_up = self.session.scalar(
            select(FollowUp).where(
                FollowUp.clinic_id == self.clinic_id,
                FollowUp.patient_id == patient_id,
                FollowUp.status.in_(("scheduled", "contacted")),
            )
        )
        recall = self.session.scalar(
            select(Recall).where(
                Recall.clinic_id == self.clinic_id,
                Recall.patient_id == patient_id,
                Recall.status.in_(("scheduled", "contacted")),
            )
        )
        result: list[tuple[str, UUID, str]] = []
        if follow_up is not None:
            result.append(("Follow-up", follow_up.id, follow_up.due_on.isoformat()))
        if recall is not None:
            result.append(("Recall", recall.id, recall.due_on.isoformat()))
        return result

    def type_page(self, after: UUID | None) -> list[AppointmentType]:
        query = select(AppointmentType).where(
            AppointmentType.clinic_id == self.clinic_id, AppointmentType.is_active.is_(True)
        )
        if after is not None:
            query = query.where(AppointmentType.id > after)
        return list(self.session.scalars(query.order_by(AppointmentType.id).limit(5)))

    def clinician_page(self, after: UUID | None) -> list[AppUser]:
        query = (
            select(AppUser)
            .join(
                UserRole,
                (UserRole.user_id == AppUser.id) & (UserRole.clinic_id == AppUser.clinic_id),
            )
            .where(
                AppUser.clinic_id == self.clinic_id,
                AppUser.is_active.is_(True),
                UserRole.clinic_id == self.clinic_id,
                UserRole.role == "clinician",
            )
        )
        if after is not None:
            query = query.where(AppUser.id > after)
        return list(self.session.scalars(query.order_by(AppUser.id).limit(5)))
