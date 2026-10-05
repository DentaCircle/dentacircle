"""Login, logout and the current user.

Login and logout are public because the caller has no session yet. Logout returns no
data. /auth/me names every role, so any signed-in user can call it and clinic_admin is
not a special case.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from dentacircle.core.access import SessionDep, public, require_roles
from dentacircle.core.config import get_settings
from dentacircle.domain.roles import ROLES
from dentacircle.services.auth_service import (
    CurrentUser,
    InvalidCredentialsError,
    login,
    logout,
)

router = APIRouter()

SESSION_COOKIE = "dc_session"

# Every role is listed, so any signed-in user passes and clinic_admin is not implicit.
any_signed_in_user = require_roles(*ROLES)


class LoginRequest(BaseModel):
    email: str
    password: str


class ClinicResponse(BaseModel):
    id: UUID
    name: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    roles: list[str]
    clinic: ClinicResponse


class LoginResponse(BaseModel):
    user: UserResponse


def user_response(user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=user.roles,
        clinic=ClinicResponse(id=user.clinic.id, name=user.clinic.name),
    )


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/auth/login")
@public
def login_route(body: LoginRequest, response: Response, session: SessionDep) -> LoginResponse:
    try:
        result = login(session, body.email, body.password, get_settings().session_ttl_hours)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401) from None
    session.commit()
    set_session_cookie(response, result.token)
    return LoginResponse(user=user_response(result.user))


@router.post("/auth/logout", status_code=204)
@public
def logout_route(request: Request, session: SessionDep) -> Response:
    logout(session, request.cookies.get(SESSION_COOKIE))
    session.commit()
    # A fresh response, so the cookie is cleared on the object we actually return.
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/auth/me")
def me(user: Annotated[CurrentUser, Depends(any_signed_in_user)]) -> UserResponse:
    return user_response(user)
