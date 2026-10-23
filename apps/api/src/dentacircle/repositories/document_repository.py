"""Reads and writes for one clinic's documents. Every query filters by that clinic."""

from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.app_user import AppUser
from dentacircle.models.document import Document


class DocumentRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add(self, document: Document) -> None:
        document.clinic_id = self._clinic_id
        self._session.add(document)

    def get_for_patient(self, patient_id: UUID, document_id: UUID) -> Document | None:
        """The document only when it belongs to this patient in this clinic."""
        statement = scoped_select(Document, self._clinic_id).where(
            Document.patient_id == patient_id, Document.id == document_id
        )
        return cast(Document | None, self._session.scalar(statement))

    def list_for_patient(
        self, patient_id: UUID, page: int, page_size: int
    ) -> tuple[list[Document], int]:
        """Newest first: created_at, then id."""
        where = (Document.clinic_id == self._clinic_id, Document.patient_id == patient_id)
        total = self._session.scalar(select(func.count()).select_from(Document).where(*where))
        statement = (
            scoped_select(Document, self._clinic_id)
            .where(Document.patient_id == patient_id)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self._session.scalars(statement)), int(total or 0)

    def uploader_names(self, user_ids: set[UUID]) -> dict[UUID, str]:
        """Names for these users, including deactivated ones."""
        if not user_ids:
            return {}
        rows = self._session.scalars(
            scoped_select(AppUser, self._clinic_id).where(AppUser.id.in_(user_ids))
        )
        return {row.id: row.full_name for row in rows}
