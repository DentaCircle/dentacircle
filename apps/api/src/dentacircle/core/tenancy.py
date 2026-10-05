"""Clinic scoping for queries.

The clinic id always comes from the caller's session, never from the request.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Select, select

from dentacircle.core.database import Base


def scoped_select(model: type[Base], clinic_id: UUID) -> Select[Any]:
    return select(model).where(model.clinic_id == clinic_id)  # type: ignore[attr-defined]
