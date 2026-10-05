"""Route access.

Health checks and login are public. Every other route names the roles that may call it,
through require_roles. A route with neither is a bug, and a test walks the app to catch it.
clinic_admin has no automatic access: a route must list it.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from dentacircle.core.database import get_session
from dentacircle.services.auth_service import CurrentUser, UnauthenticatedError, resolve_session

SessionDep = Annotated[Session, Depends(get_session)]


def public[F: Callable[..., object]](endpoint: F) -> F:
    """Mark a route as callable without a login. It must not return clinic or patient data."""
    endpoint.is_public = True  # type: ignore[attr-defined]
    return endpoint


def require_roles(*roles: str) -> Callable[..., CurrentUser]:
    """Dependency that returns the caller, or 401 / 403."""

    def dependency(request: Request, session: SessionDep) -> CurrentUser:
        token = request.cookies.get("dc_session")
        if token is None:
            raise HTTPException(status_code=401)
        try:
            user = resolve_session(session, token)
        except UnauthenticatedError:
            raise HTTPException(status_code=401) from None
        if not any(role in roles for role in user.roles):
            raise HTTPException(status_code=403)
        return user

    dependency.allowed_roles = roles  # type: ignore[attr-defined]
    return dependency
