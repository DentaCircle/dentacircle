"""Categories, items and batches. These routes do not change stock."""

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.inventory import (
    INVENTORY_READ_ROLES,
    INVENTORY_WRITE_ROLES,
    ITEM_STATUSES,
    MAX_BATCH_NUMBER_LENGTH,
    MAX_CATEGORY_NAME_LENGTH,
    MAX_ITEM_NAME_LENGTH,
    MAX_LOW_STOCK_THRESHOLD,
    MAX_UNIT_LENGTH,
    InventoryFieldError,
)
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.inventory_service import (
    BatchChanges,
    BatchView,
    CategoryView,
    DuplicateBatchError,
    DuplicateNameError,
    InvalidItemStatusError,
    InventoryNotFoundError,
    ItemChanges,
    ItemDetail,
    ItemInactiveError,
    ItemPage,
    ItemView,
    add_batch,
    create_category,
    create_item,
    edit_batch,
    edit_item,
    get_item,
    list_categories,
    list_items,
    rename_category,
    set_item_status,
)
from dentacircle.services.patient_service import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

router = APIRouter()

can_read = require_roles(*INVENTORY_READ_ROLES)
can_write = require_roles(*INVENTORY_WRITE_ROLES)

ItemStatus = Literal["active", "inactive"]
ItemListView = Literal["active", "inactive", "all"]
MAX_PAGE = (2**63 - 1) // MAX_PAGE_SIZE + 1


def _trimmed(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


def _whole(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise PydanticCustomError("int_type", "invalid")
    return value


class CategoryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_CATEGORY_NAME_LENGTH)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return _trimmed(value)


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    item_count: int


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_ITEM_NAME_LENGTH)
    category_id: UUID
    unit: str = Field(min_length=1, max_length=MAX_UNIT_LENGTH)
    low_stock_threshold: int = Field(default=0, ge=0, le=MAX_LOW_STOCK_THRESHOLD)

    @field_validator("name", "unit", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return _trimmed(value)

    @field_validator("low_stock_threshold", mode="before")
    @classmethod
    def whole_threshold(cls, value: object) -> object:
        return _whole(value)


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=MAX_ITEM_NAME_LENGTH)
    category_id: UUID | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=MAX_UNIT_LENGTH)
    low_stock_threshold: int | None = Field(default=None, ge=0, le=MAX_LOW_STOCK_THRESHOLD)

    @field_validator("name", "unit", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return _trimmed(value)

    @field_validator("low_stock_threshold", mode="before")
    @classmethod
    def whole_threshold(cls, value: object) -> object:
        return _whole(value)

    @field_validator("name", "unit", "category_id", "low_stock_threshold")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise PydanticCustomError("null_not_allowed", "invalid")
        return value

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ItemUpdate":
        if not self.model_fields_set:
            raise ValueError("empty")
        return self


class StatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "inactive"]


class CategoryLinkBody(BaseModel):
    id: UUID
    name: str


class ItemResponse(BaseModel):
    id: UUID
    name: str
    category: CategoryLinkBody
    unit: str
    low_stock_threshold: int
    status: ItemStatus
    batch_count: int


class BatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_number: str = Field(min_length=1, max_length=MAX_BATCH_NUMBER_LENGTH)
    expiry_on: date | None = None

    @field_validator("batch_number", mode="before")
    @classmethod
    def trim_number(cls, value: object) -> object:
        return _trimmed(value)


class BatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_number: str | None = Field(default=None, min_length=1, max_length=MAX_BATCH_NUMBER_LENGTH)
    expiry_on: date | None = None

    @field_validator("batch_number", mode="before")
    @classmethod
    def trim_number(cls, value: object) -> object:
        return _trimmed(value)

    @field_validator("batch_number")
    @classmethod
    def reject_null_number(cls, value: str | None) -> str:
        if value is None:
            raise PydanticCustomError("null_not_allowed", "invalid")
        return value

    @model_validator(mode="after")
    def at_least_one_field(self) -> "BatchUpdate":
        if not self.model_fields_set:
            raise ValueError("empty")
        return self


class BatchResponse(BaseModel):
    id: UUID
    batch_number: str
    expiry_on: date | None
    expired: bool
    created_at: datetime


class ItemDetailResponse(ItemResponse):
    batches: list[BatchResponse]


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    total: int
    page: int
    page_size: int


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
}
_WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    409: {"model": ErrorResponse, "description": "duplicate_name"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_STATUS_ERRORS: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    409: {"model": ErrorResponse, "description": "invalid_status"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_BATCH_ERRORS: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    409: {"model": ErrorResponse, "description": "duplicate_batch or item_inactive"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}
_LIST_ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "validation_error"},
}


@router.post("/inventory/categories", status_code=201, responses=_WRITE_ERRORS)
def post_category(
    body: CategoryBody,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> CategoryResponse:
    try:
        created = create_category(session, user.clinic.id, user.id, body.name)
    except InventoryFieldError as exc:
        raise _field_error(exc) from None
    except DuplicateNameError:
        raise CodedHttpError(409, "duplicate_name", "That name is already in use.") from None
    session.commit()
    return _category(created)


@router.get("/inventory/categories")
def get_categories(
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
) -> list[CategoryResponse]:
    return [_category(row) for row in list_categories(session, user.clinic.id)]


@router.patch("/inventory/categories/{category_id}", responses=_WRITE_ERRORS)
def patch_category(
    category_id: UUID,
    body: CategoryBody,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> CategoryResponse:
    try:
        renamed = rename_category(session, user.clinic.id, user.id, category_id, body.name)
    except InventoryFieldError as exc:
        raise _field_error(exc) from None
    except (InventoryNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    except DuplicateNameError:
        raise CodedHttpError(409, "duplicate_name", "That name is already in use.") from None
    session.commit()
    return _category(renamed)


@router.post("/inventory/items", status_code=201, responses=_WRITE_ERRORS)
def post_item(
    body: ItemCreate,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> ItemResponse:
    try:
        created = create_item(
            session,
            user.clinic.id,
            user.id,
            body.name,
            body.category_id,
            body.unit,
            body.low_stock_threshold,
        )
    except InventoryFieldError as exc:
        raise _field_error(exc) from None
    except (InventoryNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    except DuplicateNameError:
        raise CodedHttpError(409, "duplicate_name", "That name is already in use.") from None
    session.commit()
    return _item(created)


@router.get("/inventory/items", responses=_LIST_ERRORS)
def get_items(
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
    status: Annotated[ItemListView, Query()] = "active",
    category_id: Annotated[UUID | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> ItemListResponse:
    found = list_items(session, user.clinic.id, status, category_id, q, page, page_size)
    return _page(found)


@router.get("/inventory/items/{item_id}", responses=_NOT_FOUND)
def get_one_item(
    item_id: UUID,
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
) -> ItemDetailResponse:
    try:
        found = get_item(session, user.clinic.id, item_id, datetime.now(UTC))
    except (InventoryNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    return _detail(found)


@router.patch("/inventory/items/{item_id}", responses=_WRITE_ERRORS)
def patch_item(
    item_id: UUID,
    body: ItemUpdate,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> ItemResponse:
    try:
        updated = edit_item(
            session,
            user.clinic.id,
            user.id,
            item_id,
            ItemChanges(
                fields=frozenset(body.model_fields_set),
                name=body.name,
                category_id=body.category_id,
                unit=body.unit,
                low_stock_threshold=body.low_stock_threshold,
            ),
        )
    except InventoryFieldError as exc:
        raise _field_error(exc) from None
    except (InventoryNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    except DuplicateNameError:
        raise CodedHttpError(409, "duplicate_name", "That name is already in use.") from None
    session.commit()
    return _item(updated)


@router.post("/inventory/items/{item_id}/status", responses=_STATUS_ERRORS)
def post_item_status(
    item_id: UUID,
    body: StatusBody,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> ItemResponse:
    try:
        updated = set_item_status(session, user.clinic.id, user.id, item_id, body.status)
    except InventoryFieldError as exc:
        raise _field_error(exc) from None
    except (InventoryNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    except InvalidItemStatusError:
        raise CodedHttpError(409, "invalid_status", "This item already has that status.") from None
    session.commit()
    return _item(updated)


@router.post("/inventory/items/{item_id}/batches", status_code=201, responses=_BATCH_ERRORS)
def post_batch(
    item_id: UUID,
    body: BatchCreate,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> BatchResponse:
    try:
        created = add_batch(
            session,
            user.clinic.id,
            user.id,
            item_id,
            body.batch_number,
            body.expiry_on,
            datetime.now(UTC),
        )
    except InventoryFieldError as exc:
        raise _field_error(exc) from None
    except (InventoryNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    except ItemInactiveError:
        raise CodedHttpError(409, "item_inactive", "This item is inactive.") from None
    except DuplicateBatchError:
        raise CodedHttpError(
            409, "duplicate_batch", "That batch number is already in use."
        ) from None
    session.commit()
    return _batch(created)


@router.patch("/inventory/batches/{batch_id}", responses=_BATCH_ERRORS)
def patch_batch(
    batch_id: UUID,
    body: BatchUpdate,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> BatchResponse:
    try:
        updated = edit_batch(
            session,
            user.clinic.id,
            user.id,
            batch_id,
            BatchChanges(
                fields=frozenset(body.model_fields_set),
                batch_number=body.batch_number,
                expiry_on=body.expiry_on,
            ),
            datetime.now(UTC),
        )
    except InventoryFieldError as exc:
        raise _field_error(exc) from None
    except (InventoryNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    except DuplicateBatchError:
        raise CodedHttpError(
            409, "duplicate_batch", "That batch number is already in use."
        ) from None
    session.commit()
    return _batch(updated)


def _field_error(exc: InventoryFieldError) -> RequestValidationError:
    return RequestValidationError(
        [{"type": exc.code, "loc": ("body", exc.field), "msg": exc.code, "input": None}]
    )


def _category(row: CategoryView) -> CategoryResponse:
    return CategoryResponse(id=row.id, name=row.name, item_count=row.item_count)


def _item(row: ItemView) -> ItemResponse:
    if row.status not in ITEM_STATUSES:
        raise RuntimeError("inventory item has an unknown status")
    status: ItemStatus = "active" if row.status == "active" else "inactive"
    return ItemResponse(
        id=row.id,
        name=row.name,
        category=CategoryLinkBody(id=row.category.id, name=row.category.name),
        unit=row.unit,
        low_stock_threshold=row.low_stock_threshold,
        status=status,
        batch_count=row.batch_count,
    )


def _detail(found: ItemDetail) -> ItemDetailResponse:
    item = _item(found.item)
    return ItemDetailResponse(
        **item.model_dump(), batches=[_batch(batch) for batch in found.batches]
    )


def _batch(row: BatchView) -> BatchResponse:
    return BatchResponse(
        id=row.id,
        batch_number=row.batch_number,
        expiry_on=row.expiry_on,
        expired=row.expired,
        created_at=row.created_at,
    )


def _page(found: ItemPage) -> ItemListResponse:
    return ItemListResponse(
        items=[_item(row) for row in found.items],
        total=found.total,
        page=found.page,
        page_size=found.page_size,
    )
