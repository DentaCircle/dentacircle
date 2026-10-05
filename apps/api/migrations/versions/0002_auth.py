"""Clinic, user, role and session.

Revision ID: 0002_auth
Revises: 0001_baseline
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLES = ("clinician", "receptionist", "inventory_admin", "clinic_admin")


def upgrade() -> None:
    op.create_table(
        "clinic",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinic")),
    )
    op.create_table(
        "app_user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinic.id"], name=op.f("fk_app_user_clinic_id_clinic")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_app_user_id_clinic_id"),
    )
    op.create_index(op.f("ix_app_user_clinic_id"), "app_user", ["clinic_id"])
    op.create_index("uq_app_user_email", "app_user", [sa.text("lower(email)")], unique=True)
    op.create_table(
        "user_role",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN (" + ", ".join(f"'{role}'" for role in _ROLES) + ")",
            name=op.f("ck_user_role_role_known"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "user_id"],
            ["app_user.clinic_id", "app_user.id"],
            name=op.f("fk_user_role_clinic_id_app_user"),
        ),
        sa.PrimaryKeyConstraint("user_id", "role", name=op.f("pk_user_role")),
    )
    op.create_index(op.f("ix_user_role_clinic_id"), "user_role", ["clinic_id"])
    op.create_table(
        "auth_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "user_id"],
            ["app_user.clinic_id", "app_user.id"],
            name=op.f("fk_auth_session_clinic_id_app_user"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_session_token_hash")),
    )
    op.create_index(op.f("ix_auth_session_clinic_id"), "auth_session", ["clinic_id"])
    op.create_index("ix_auth_session_user_id", "auth_session", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_session_user_id", table_name="auth_session")
    op.drop_index(op.f("ix_auth_session_clinic_id"), table_name="auth_session")
    op.drop_table("auth_session")
    op.drop_index(op.f("ix_user_role_clinic_id"), table_name="user_role")
    op.drop_table("user_role")
    op.drop_index("uq_app_user_email", table_name="app_user")
    op.drop_index(op.f("ix_app_user_clinic_id"), table_name="app_user")
    op.drop_table("app_user")
    op.drop_table("clinic")
