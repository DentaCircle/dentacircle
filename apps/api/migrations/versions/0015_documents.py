"""Documents attached to a patient. Additive. No backfill.

Revision ID: 0015_documents
Revises: 0014_timeline
Create Date: 2026-10-23

Downgrade drops the table and nothing else. The stored files are not touched.
Types and limits are frozen here. A later change needs a new revision.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_documents"
down_revision: str | None = "0014_timeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = ("application/pdf", "image/png", "image/jpeg")
_MAX_BYTES = 8 * 1024 * 1024


def upgrade() -> None:
    op.create_table(
        "document",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(filename) BETWEEN 1 AND 200",
            name=op.f("ck_document_filename_length"),
        ),
        sa.CheckConstraint(
            "content_type IN (" + ", ".join(f"'{content_type}'" for content_type in _TYPES) + ")",
            name=op.f("ck_document_content_type_known"),
        ),
        sa.CheckConstraint(
            f"size_bytes BETWEEN 1 AND {_MAX_BYTES}",
            name=op.f("ck_document_size_in_range"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinic.id"],
            name=op.f("fk_document_clinic_id_clinic"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patient.id", "patient.clinic_id"],
            name="fk_document_patient_id_clinic_id",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id", "clinic_id"],
            ["app_user.id", "app_user.clinic_id"],
            name="fk_document_uploaded_by_user_id_clinic_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document")),
        sa.UniqueConstraint("id", "clinic_id", name="uq_document_id_clinic_id"),
        sa.UniqueConstraint("storage_key", name="uq_document_storage_key"),
    )
    op.execute(
        "CREATE INDEX ix_document_patient_order ON document"
        " (clinic_id, patient_id, created_at DESC, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_patient_order")
    op.drop_table("document")
