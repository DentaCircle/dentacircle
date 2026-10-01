"""Public health checks.

These routes are open without a login so a load balancer or CI can call them.
They return no clinic or patient data. Every other route must declare its roles.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.requests import Request

from dentacircle.core.access import public
from dentacircle.core.database import get_session
from dentacircle.core.request_id import current_request_id
from dentacircle.services.health_service import DatabaseNotReady, database_is_ready

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


class HealthResponse(BaseModel):
    status: str


@router.get("/health")
@public
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready")
@public
def ready(request: Request, session: SessionDep) -> HealthResponse:
    try:
        database_is_ready(session, current_request_id(request))
    except DatabaseNotReady:
        raise HTTPException(status_code=503, detail="Database is not ready.") from None
    return HealthResponse(status="ok")
