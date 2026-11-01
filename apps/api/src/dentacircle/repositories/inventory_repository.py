"""Reads and writes for one clinic's inventory. Every query filters by that clinic."""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.orm import Session

from dentacircle.core.tenancy import scoped_select
from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.inventory_batch import InventoryBatch
from dentacircle.models.inventory_category import InventoryCategory
from dentacircle.models.inventory_item import InventoryItem
from dentacircle.models.inventory_transaction import InventoryTransaction
from dentacircle.models.procedure_resource_rule import ProcedureResourceRule


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

    def add_transaction(self, transaction: InventoryTransaction) -> None:
        transaction.clinic_id = self._clinic_id
        self._session.add(transaction)

    def add_rule(self, rule: ProcedureResourceRule) -> None:
        rule.clinic_id = self._clinic_id
        self._session.add(rule)

    def get_rule(self, type_id: UUID, item_id: UUID) -> ProcedureResourceRule | None:
        statement = scoped_select(ProcedureResourceRule, self._clinic_id).where(
            ProcedureResourceRule.appointment_type_id == type_id,
            ProcedureResourceRule.item_id == item_id,
        )
        return self._session.scalars(statement).one_or_none()

    def list_rules(self, type_id: UUID) -> list[tuple[ProcedureResourceRule, str]]:
        """Rules for one visit type, sorted by item name."""
        statement = (
            select(ProcedureResourceRule, InventoryItem.name)
            .join(InventoryItem, _same_clinic_rule_item())
            .where(
                ProcedureResourceRule.clinic_id == self._clinic_id,
                InventoryItem.clinic_id == self._clinic_id,
                ProcedureResourceRule.appointment_type_id == type_id,
            )
            .order_by(func.lower(InventoryItem.name), InventoryItem.name, ProcedureResourceRule.id)
        )
        rows = self._session.execute(statement).all()
        return [(rule, name) for rule, name in rows]

    def delete_rule(self, rule: ProcedureResourceRule) -> None:
        self._session.delete(rule)

    def lock_batches_for_items(self, item_ids: Sequence[UUID]) -> list[InventoryBatch]:
        """Lock this clinic's batches for these items, in id order.

        The caller already holds the visit row. Locking by id keeps two
        completions, and a completion beside an adjustment, from deadlocking.
        """
        statement = (
            scoped_select(InventoryBatch, self._clinic_id)
            .where(InventoryBatch.item_id.in_(tuple(item_ids)))
            .order_by(InventoryBatch.id.asc())
            .with_for_update()
        )
        return list(self._session.scalars(statement))

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
        today: date,
        alert: str | None,
    ) -> tuple[list[tuple[InventoryItem, InventoryCategory, int, int, int, bool, bool]], int]:
        # Aggregate each batch first: expiry alerts depend on its net quantity.
        batches = (
            select(
                InventoryBatch.id.label("id"),
                InventoryBatch.item_id.label("item_id"),
                InventoryBatch.expiry_on.label("expiry_on"),
                func.coalesce(func.sum(InventoryTransaction.quantity_change), 0).label("quantity"),
            )
            .outerjoin(InventoryTransaction, _same_clinic_batch())
            .where(InventoryBatch.clinic_id == self._clinic_id)
            .group_by(InventoryBatch.id, InventoryBatch.item_id, InventoryBatch.expiry_on)
            .subquery()
        )
        summary = (
            select(
                batches.c.item_id,
                func.count().label("batch_count"),
                func.sum(batches.c.quantity).label("stock"),
                func.sum(
                    case(
                        (
                            or_(batches.c.expiry_on.is_(None), batches.c.expiry_on >= today),
                            batches.c.quantity,
                        ),
                        else_=0,
                    )
                ).label("usable"),
                func.max(
                    case((and_(batches.c.quantity > 0, batches.c.expiry_on < today), 1), else_=0)
                ).label("expired"),
                func.max(
                    case(
                        (
                            and_(
                                batches.c.quantity > 0,
                                batches.c.expiry_on >= today,
                                batches.c.expiry_on <= today + timedelta(days=30),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("soon"),
            )
            .group_by(batches.c.item_id)
            .subquery()
        )
        count = func.coalesce(summary.c.batch_count, 0)
        stock = func.coalesce(summary.c.stock, 0)
        usable = func.coalesce(summary.c.usable, 0)
        expired = func.coalesce(summary.c.expired, 0) == 1
        soon = func.coalesce(summary.c.soon, 0) == 1
        active = InventoryItem.status == "active"
        alert_filters = {
            "out_of_stock": and_(active, usable == 0),
            "low_stock": and_(
                active,
                usable > 0,
                InventoryItem.low_stock_threshold > 0,
                usable <= InventoryItem.low_stock_threshold,
            ),
            "expired": and_(active, expired),
            "expiring_soon": and_(active, soon),
        }
        filters = [InventoryItem.clinic_id == self._clinic_id]
        if status is not None:
            filters.append(InventoryItem.status == status)
        if category_id is not None:
            filters.append(InventoryItem.category_id == category_id)
        if query is not None:
            filters.append(InventoryItem.name.ilike(_contains(query), escape="\\"))
        if alert == "attention":
            filters.append(or_(*alert_filters.values()))
        elif alert is not None:
            filters.append(alert_filters[alert])
        base = (
            select(InventoryItem, InventoryCategory, count, stock, usable, expired, soon)
            .join(
                InventoryCategory,
                (InventoryCategory.id == InventoryItem.category_id)
                & (InventoryCategory.clinic_id == InventoryItem.clinic_id),
            )
            .outerjoin(summary, summary.c.item_id == InventoryItem.id)
            .where(*filters)
        )
        total = self._session.scalar(select(func.count()).select_from(base.subquery()))
        rows = self._session.execute(
            base.order_by(func.lower(InventoryItem.name), InventoryItem.name, InventoryItem.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [
            (
                item,
                category,
                int(n),
                int(total_stock),
                int(usable_stock),
                bool(old),
                bool(soon_flag),
            )
            for item, category, n, total_stock, usable_stock, old, soon_flag in rows
        ], int(total or 0)

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

    def batch_quantity(self, batch_id: UUID) -> int:
        """Sum of this clinic's movements for one batch. Zero when there are none."""
        total = self._session.scalar(
            select(func.coalesce(func.sum(InventoryTransaction.quantity_change), 0)).where(
                InventoryTransaction.clinic_id == self._clinic_id,
                InventoryTransaction.batch_id == batch_id,
            )
        )
        return int(total or 0)

    def item_stock(self, item_id: UUID) -> int:
        """Sum across every batch of the item, including expired batches."""
        total = self._session.scalar(
            select(func.coalesce(func.sum(InventoryTransaction.quantity_change), 0))
            .select_from(InventoryTransaction)
            .join(InventoryBatch, _same_clinic_batch())
            .where(
                InventoryTransaction.clinic_id == self._clinic_id,
                InventoryBatch.clinic_id == self._clinic_id,
                InventoryBatch.item_id == item_id,
            )
        )
        return int(total or 0)

    def batch_quantities(self, item_id: UUID) -> dict[UUID, int]:
        statement = (
            select(
                InventoryTransaction.batch_id,
                func.coalesce(func.sum(InventoryTransaction.quantity_change), 0),
            )
            .join(InventoryBatch, _same_clinic_batch())
            .where(
                InventoryTransaction.clinic_id == self._clinic_id,
                InventoryBatch.clinic_id == self._clinic_id,
                InventoryBatch.item_id == item_id,
            )
            .group_by(InventoryTransaction.batch_id)
        )
        rows = self._session.execute(statement).all()
        return {batch_id: int(total) for batch_id, total in rows}

    def list_transactions(
        self, item_id: UUID, page: int, page_size: int
    ) -> tuple[list[tuple[InventoryTransaction, str, str, datetime | None]], int]:
        """Newest first. The batch number, staff name and visit time come from this clinic."""
        filters = (
            InventoryTransaction.clinic_id == self._clinic_id,
            InventoryBatch.clinic_id == self._clinic_id,
            InventoryBatch.item_id == item_id,
            AppUser.clinic_id == self._clinic_id,
        )
        joined = (
            select(
                InventoryTransaction,
                InventoryBatch.batch_number,
                AppUser.full_name,
                Appointment.starts_at,
            )
            .join(InventoryBatch, _same_clinic_batch())
            .join(AppUser, _same_clinic_user())
            .outerjoin(Appointment, _same_clinic_appointment())
            .where(*filters)
        )
        total = self._session.scalar(select(func.count()).select_from(joined.subquery()))
        statement = (
            joined.order_by(
                InventoryTransaction.created_at.desc(),
                InventoryTransaction.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = self._session.execute(statement).all()
        return [
            (row, batch_number, recorded_by, starts_at)
            for row, batch_number, recorded_by, starts_at in rows
        ], int(total or 0)


def _same_clinic_batch() -> ColumnElement[bool]:
    return (InventoryBatch.id == InventoryTransaction.batch_id) & (
        InventoryBatch.clinic_id == InventoryTransaction.clinic_id
    )


def _same_clinic_user() -> ColumnElement[bool]:
    return (AppUser.id == InventoryTransaction.created_by_user_id) & (
        AppUser.clinic_id == InventoryTransaction.clinic_id
    )


def _same_clinic_appointment() -> ColumnElement[bool]:
    return (Appointment.id == InventoryTransaction.appointment_id) & (
        Appointment.clinic_id == InventoryTransaction.clinic_id
    )


def _same_clinic_rule_item() -> ColumnElement[bool]:
    return (InventoryItem.id == ProcedureResourceRule.item_id) & (
        InventoryItem.clinic_id == ProcedureResourceRule.clinic_id
    )


def _contains(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
