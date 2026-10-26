"""Rules that say which stock a visit type uses when the visit is completed."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.core.errors import CodedHttpError
from dentacircle.domain.inventory import (
    INVENTORY_READ_ROLES,
    INVENTORY_WRITE_ROLES,
    MAX_RULE_QUANTITY,
    InventoryFieldError,
)
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.clinic_day_service import ClinicNotFoundError
from dentacircle.services.inventory_service import (
    InventoryNotFoundError,
    ItemInactiveError,
    ResourceRuleView,
    list_resource_rules,
    remove_resource_rule,
    set_resource_rule,
)

router = APIRouter()

can_read = require_roles(*INVENTORY_READ_ROLES)
can_write = require_roles(*INVENTORY_WRITE_ROLES)


def _whole(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PydanticCustomError("int_type", "invalid")
    return value


class RuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=1, le=MAX_RULE_QUANTITY)

    @field_validator("quantity", mode="before")
    @classmethod
    def whole_quantity(cls, value: object) -> object:
        return _whole(value)


class RuleResponse(BaseModel):
    item_id: UUID
    item_name: str
    quantity: int


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not Found"},
}
_WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_READ_ERRORS,
    409: {"model": ErrorResponse, "description": "item_inactive"},
    422: {"model": ErrorResponse, "description": "validation_error"},
}


def _rule(row: ResourceRuleView) -> RuleResponse:
    return RuleResponse(item_id=row.item_id, item_name=row.item_name, quantity=row.quantity)


def _field_error(exc: InventoryFieldError) -> RequestValidationError:
    return RequestValidationError(
        [{"type": exc.code, "loc": ("body", exc.field), "msg": exc.code, "input": None}]
    )


@router.get(
    "/appointment-types/{type_id}/resource-rules",
    responses=_READ_ERRORS,
)
def get_resource_rules(
    type_id: UUID,
    user: Annotated[CurrentUser, Depends(can_read)],
    session: SessionDep,
) -> list[RuleResponse]:
    try:
        rows = list_resource_rules(session, user.clinic.id, type_id)
    except (InventoryNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    return [_rule(row) for row in rows]


@router.put(
    "/appointment-types/{type_id}/resource-rules/{item_id}",
    responses=_WRITE_ERRORS,
)
def put_resource_rule(
    type_id: UUID,
    item_id: UUID,
    body: RuleBody,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> RuleResponse:
    try:
        saved = set_resource_rule(
            session,
            user.clinic.id,
            user.id,
            type_id,
            item_id,
            body.quantity,
        )
    except InventoryFieldError as exc:
        raise _field_error(exc) from None
    except (InventoryNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    except ItemInactiveError:
        raise CodedHttpError(409, "item_inactive", "This item is inactive.") from None
    session.commit()
    return _rule(saved)


@router.delete(
    "/appointment-types/{type_id}/resource-rules/{item_id}",
    status_code=204,
    responses=_READ_ERRORS,
)
def delete_resource_rule(
    type_id: UUID,
    item_id: UUID,
    user: Annotated[CurrentUser, Depends(can_write)],
    session: SessionDep,
) -> Response:
    try:
        remove_resource_rule(session, user.clinic.id, user.id, type_id, item_id)
    except (InventoryNotFoundError, ClinicNotFoundError):
        raise HTTPException(status_code=404) from None
    session.commit()
    return Response(status_code=204)
