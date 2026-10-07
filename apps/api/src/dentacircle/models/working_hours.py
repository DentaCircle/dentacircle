"""Open intervals for one clinic. Several per weekday, so a break is a gap."""

from datetime import time

from sqlalchemy import CheckConstraint, PrimaryKeyConstraint, SmallInteger, Time
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import literal_column

from dentacircle.core.database import Base
from dentacircle.models.mixins import ClinicScoped


class ClinicWorkingHours(ClinicScoped, Base):
    __tablename__ = "clinic_working_hours"
    __table_args__ = (
        PrimaryKeyConstraint("clinic_id", "weekday", "opens_at"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("opens_at < closes_at", name="opens_before_closes"),
        # Inclusive bounds, so 12:00–12:00 touching counts as an overlap.
        ExcludeConstraint(
            ("clinic_id", "="),
            ("weekday", "="),
            (literal_column("timerange(opens_at, closes_at, '[]')"), "&&"),
            name="ex_clinic_working_hours_no_overlap",
            using="gist",
        ),
    )

    weekday: Mapped[int] = mapped_column(SmallInteger)
    opens_at: Mapped[time] = mapped_column(Time)
    closes_at: Mapped[time] = mapped_column(Time)
