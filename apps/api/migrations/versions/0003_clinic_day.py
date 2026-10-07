"""Clinic timezone, working hours and appointment types.

Revision ID: 0003_clinic_day
Revises: 0002_auth
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from dentacircle.domain.clinic_day import (
    DEFAULT_APPOINTMENT_MINUTES,
    DEFAULT_APPOINTMENT_TYPES,
    DEFAULT_TIMEZONE,
    DEFAULT_WORKING_HOURS,
)

revision: str = "0003_clinic_day"
down_revision: str | None = "0002_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE TYPE timerange AS RANGE (subtype = time)")
    op.add_column(
        "clinic",
        sa.Column(
            "timezone",
            sa.Text(),
            server_default=sa.text(f"'{DEFAULT_TIMEZONE}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "clinic",
        sa.Column(
            "default_appointment_minutes",
            sa.Integer(),
            server_default=sa.text(str(DEFAULT_APPOINTMENT_MINUTES)),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_clinic_default_appointment_minutes_range",
        "clinic",
        "default_appointment_minutes BETWEEN 5 AND 480",
    )
    op.create_table(
        "clinic_working_hours",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=False),
        sa.Column("closes_at", sa.Time(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6",
            name=op.f("ck_clinic_working_hours_weekday_range"),
        ),
        sa.CheckConstraint(
            "opens_at < closes_at", name=op.f("ck_clinic_working_hours_opens_before_closes")
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_clinic_working_hours_clinic_id_clinic"),
        ),
        sa.PrimaryKeyConstraint(
            "clinic_id", "weekday", "opens_at", name=op.f("pk_clinic_working_hours")
        ),
    )
    op.create_index(
        op.f("ix_clinic_working_hours_clinic_id"), "clinic_working_hours", ["clinic_id"]
    )
    op.execute(
        "ALTER TABLE clinic_working_hours ADD CONSTRAINT ex_clinic_working_hours_no_overlap "
        "EXCLUDE USING gist ("
        "clinic_id WITH =, "
        "weekday WITH =, "
        "timerange(opens_at, closes_at, '[]') WITH &&)"
    )
    op.create_table(
        "appointment_type",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "duration_minutes IS NULL OR (duration_minutes BETWEEN 5 AND 480)",
            name=op.f("ck_appointment_type_duration_range"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinic.id"], name=op.f("fk_appointment_type_clinic_id_clinic")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointment_type")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_appointment_type_id_clinic_id"),
    )
    op.create_index(op.f("ix_appointment_type_clinic_id"), "appointment_type", ["clinic_id"])
    op.create_index(
        "uq_appointment_type_name",
        "appointment_type",
        ["clinic_id", sa.text("lower(name)")],
        unique=True,
    )
    _seed_existing_clinics()


def downgrade() -> None:
    op.drop_index("uq_appointment_type_name", table_name="appointment_type")
    op.drop_index(op.f("ix_appointment_type_clinic_id"), table_name="appointment_type")
    op.drop_table("appointment_type")
    op.drop_index(op.f("ix_clinic_working_hours_clinic_id"), table_name="clinic_working_hours")
    op.drop_table("clinic_working_hours")
    op.drop_constraint("ck_clinic_default_appointment_minutes_range", "clinic", type_="check")
    op.drop_column("clinic", "default_appointment_minutes")
    op.drop_column("clinic", "timezone")
    op.execute("DROP TYPE IF EXISTS timerange")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")


def _seed_existing_clinics() -> None:
    bind = op.get_bind()
    for interval in DEFAULT_WORKING_HOURS:
        bind.execute(
            sa.text(
                "INSERT INTO clinic_working_hours (clinic_id, weekday, opens_at, closes_at)"
                " SELECT id, :weekday, :opens_at, :closes_at FROM clinic"
            ),
            {
                "weekday": interval.weekday,
                "opens_at": interval.opens_at,
                "closes_at": interval.closes_at,
            },
        )
    for appointment_type in DEFAULT_APPOINTMENT_TYPES:
        bind.execute(
            sa.text(
                "INSERT INTO appointment_type"
                " (id, clinic_id, name, duration_minutes, is_active)"
                " SELECT gen_random_uuid(), id, :name, :duration, true FROM clinic"
            ),
            {"name": appointment_type.name, "duration": appointment_type.duration_minutes},
        )
