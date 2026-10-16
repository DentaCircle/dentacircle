"""One care item marked started or completed in a session."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from dentacircle.core.database import Base
from dentacircle.domain.care_session import SESSION_RESULT_STATUSES
from dentacircle.models.mixins import ClinicScoped

_RESULTS = ", ".join(f"'{status}'" for status in SESSION_RESULT_STATUSES)


class CareSessionItem(ClinicScoped, Base):
    __tablename__ = "care_session_item"
    __table_args__ = (
        CheckConstraint(f"status IN ({_RESULTS})", name="status_known"),
        UniqueConstraint(
            "care_session_id", "care_item_id", name="uq_care_session_item_session_item"
        ),
        ForeignKeyConstraint(
            ["care_session_id", "clinic_id"],
            ["care_session.id", "care_session.clinic_id"],
            name="fk_care_session_item_session_id_clinic_id",
        ),
        ForeignKeyConstraint(
            ["care_item_id", "clinic_id"],
            ["care_item.id", "care_item.clinic_id"],
            name="fk_care_session_item_care_item_id_clinic_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    care_session_id: Mapped[UUID] = mapped_column()
    care_item_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(Text)
