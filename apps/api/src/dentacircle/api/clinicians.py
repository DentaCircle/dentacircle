"""Active clinicians in the caller's clinic. Names only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dentacircle.core.access import SessionDep, require_roles
from dentacircle.domain.appointment import APPOINTMENT_ROLES
from dentacircle.services.appointment_service import list_clinicians
from dentacircle.services.auth_service import CurrentUser

router = APIRouter()

can_book = require_roles(*APPOINTMENT_ROLES)


class ClinicianResponse(BaseModel):
    id: UUID
    full_name: str


@router.get("/clinicians")
def get_clinicians(
    user: Annotated[CurrentUser, Depends(can_book)],
    session: SessionDep,
) -> list[ClinicianResponse]:
    rows = list_clinicians(session, user.clinic.id)
    return [ClinicianResponse(id=row.id, full_name=row.full_name) for row in rows]
