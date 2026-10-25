"""Reads and writes for one clinic's inventory. Every query filters by that clinic."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.inventory_batch import InventoryBatch
from dentacircle.models.inventory_category import InventoryCategory
from dentacircle.models.inventory_item import InventoryItem


class InventoryRepository:
    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    def add_category(self, category: InventoryCategory) -> None:
        category.clinic_id = self._clinic_id
        self._session.add(category)

    def add_item(self, item: InventoryItem) -> None:
        item.clinic_id = self._clinic_id
        self._session.add(item)

    def add_batch(self, batch: InventoryBatch) -> None:
        batch.clinic_id = self._clinic_id
        self._session.add(batch)

    def get_category(self, category_id: UUID, *, lock: bool = False) -> InventoryCategory | None:
        statement = scoped_select(InventoryCategory, self._clinic_id).where(
            InventoryCategory.id == category_id
        )
        if lock:
            statement = statement.with_for_update()
        return self._session.scalars(statement).one_or_none()

    def find_category_by_name(self, name: str) -> InventoryCategory | None:
        statement = scoped_select(InventoryCategory, self._clinic_id).where(
            func.lower(InventoryCategory.name) == name.strip().lower()
        )
        return self._session.scalars(statement).one_or_none()

    def list_categories(self) -> list[tuple[InventoryCategory, int]]:
        item_count = (
            select(func.count(InventoryItem.id))
            .where(
                InventoryItem.category_id == InventoryCategory.id,
                InventoryItem.clinic_id == self._clinic_id,
            )
            .correlate(InventoryCategory)
            .scalar_subquery()
        )
        statement = (
            select(InventoryCategory, item_count)
            .where(InventoryCategory.clinic_id == self._clinic_id)
            .order_by(func.lower(InventoryCategory.name), InventoryCategory.name)
        )
        rows = self._session.execute(statement).all()
        return [(category, int(count)) for category, count in rows]

    def get_item(self, item_id: UUID, *, lock: bool = False) -> InventoryItem | None:
        statement = scoped_select(InventoryItem, self._clinic_id).where(InventoryItem.id == item_id)
        if lock:
            statement = statement.with_for_update()
        return self._session.scalars(statement).one_or_none()

    def get_item_with_category(
        self, item_id: UUID
    ) -> tuple[InventoryItem, InventoryCategory] | None:
        """The item and its category, both in this clinic. Another clinic's id is missing."""
        statement = (
            select(InventoryItem, InventoryCategory)
            .join(
                InventoryCategory,
                (InventoryCategory.id == InventoryItem.category_id)
                & (InventoryCategory.clinic_id == InventoryItem.clinic_id),
            )
            .where(InventoryItem.clinic_id == self._clinic_id, InventoryItem.id == item_id)
        )
        found = self._session.execute(statement).one_or_none()
        if found is None:
            return None
        item, category = found
        return item, category

    def find_item_by_name(self, name: str) -> InventoryItem | None:
        statement = scoped_select(InventoryItem, self._clinic_id).where(
            func.lower(InventoryItem.name) == name.strip().lower()
        )
        return self._session.scalars(statement).one_or_none()

    def list_items(
        self,
        status: str | None,
        category_id: UUID | None,
        query: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[InventoryItem, InventoryCategory, int]], int]:
        batch_count = (
            select(func.count(InventoryBatch.id))
            .where(
                InventoryBatch.item_id == InventoryItem.id,
                InventoryBatch.clinic_id == self._clinic_id,
            )
            .correlate(InventoryItem)
            .scalar_subquery()
        )
        filters = [InventoryItem.clinic_id == self._clinic_id]
        if status is not None:
            filters.append(InventoryItem.status == status)
        if category_id is not None:
            filters.append(InventoryItem.category_id == category_id)
        if query is not None:
            filters.append(InventoryItem.name.ilike(_contains(query), escape="\\"))
        total = self._session.scalar(
            select(func.count()).select_from(InventoryItem).where(*filters)
        )
        statement = (
            select(InventoryItem, InventoryCategory, batch_count)
            .join(
                InventoryCategory,
                (InventoryCategory.id == InventoryItem.category_id)
                & (InventoryCategory.clinic_id == InventoryItem.clinic_id),
            )
            .where(*filters)
            .order_by(func.lower(InventoryItem.name), InventoryItem.name, InventoryItem.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = self._session.execute(statement).all()
        return [(item, category, int(count)) for item, category, count in rows], int(total or 0)

    def category_for_item(self, item: InventoryItem) -> InventoryCategory | None:
        return self.get_category(item.category_id)

    def batch_count(self, item_id: UUID) -> int:
        total = self._session.scalar(
            select(func.count())
            .select_from(InventoryBatch)
            .where(
                InventoryBatch.clinic_id == self._clinic_id,
                InventoryBatch.item_id == item_id,
            )
        )
        return int(total or 0)

    def get_batch(self, batch_id: UUID, *, lock: bool = False) -> InventoryBatch | None:
        statement = scoped_select(InventoryBatch, self._clinic_id).where(
            InventoryBatch.id == batch_id
        )
        if lock:
            statement = statement.with_for_update()
        return self._session.scalars(statement).one_or_none()

    def find_batch_by_number(self, item_id: UUID, batch_number: str) -> InventoryBatch | None:
        statement = scoped_select(InventoryBatch, self._clinic_id).where(
            InventoryBatch.item_id == item_id,
            func.lower(InventoryBatch.batch_number) == batch_number.strip().lower(),
        )
        return self._session.scalars(statement).one_or_none()

    def list_batches(self, item_id: UUID) -> list[InventoryBatch]:
        """Earliest expiry first. A batch with no expiry is last. Newest created wins a tie."""
        statement = (
            scoped_select(InventoryBatch, self._clinic_id)
            .where(InventoryBatch.item_id == item_id)
            .order_by(
                InventoryBatch.expiry_on.asc().nulls_last(),
                InventoryBatch.created_at.desc(),
                InventoryBatch.id.desc(),
            )
        )
        return list(self._session.scalars(statement))


def _contains(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
