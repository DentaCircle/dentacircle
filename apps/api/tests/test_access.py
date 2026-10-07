"""Role checks, and the rule that every route is public or role-protected."""

from collections.abc import Iterable, Iterator
from typing import Annotated

import pytest
from alembic import command
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from dentacircle.api.auth import router as auth_router
from dentacircle.core.access import public, require_roles
from dentacircle.core.database import clear_engine, get_engine
from dentacircle.core.errors import register_exception_handlers
from dentacircle.core.request_context import RequestContextMiddleware
from dentacircle.services.auth_service import CurrentUser
from dentacircle.services.provisioning_service import create_user, get_or_create_clinic
from tests.test_migrations import _config

_PASSWORD = "synthetic-password-marker"


@pytest.fixture
def client(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    command.upgrade(_config(), "head")
    clear_engine()
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, "Synthetic Clinic")
        create_user(
            session,
            clinic.id,
            "both@x.test",
            "Synthetic Person",
            _PASSWORD,
            ["clinician", "receptionist"],
        )
        create_user(
            session, clinic.id, "admin@x.test", "Synthetic Admin", _PASSWORD, ["clinic_admin"]
        )
        session.commit()

    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestContextMiddleware)
    application.include_router(auth_router)

    @application.get("/clinicians-only")
    def clinicians_only(
        user: Annotated[CurrentUser, Depends(require_roles("clinician"))],
    ) -> dict[str, str]:
        return {"email": user.email}

    with TestClient(application) as test_client:
        yield test_client


def test_no_session_is_rejected(client: TestClient) -> None:
    response = client.get("/clinicians-only")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_a_listed_role_passes(client: TestClient) -> None:
    cookie = _login(client, "both@x.test")
    response = client.get("/clinicians-only", cookies={"dc_session": cookie})
    assert response.status_code == 200
    assert response.json()["email"] == "both@x.test"


def test_one_of_two_roles_is_enough(client: TestClient) -> None:
    """both@x.test holds clinician and receptionist. The route lists only clinician."""
    cookie = _login(client, "both@x.test")
    response = client.get("/clinicians-only", cookies={"dc_session": cookie})
    assert response.status_code == 200


def test_an_unlisted_role_is_forbidden_even_for_clinic_admin(client: TestClient) -> None:
    cookie = _login(client, "admin@x.test")
    response = client.get("/clinicians-only", cookies={"dc_session": cookie})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_every_route_is_public_or_role_protected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    from dentacircle.main import create_app

    assert unmarked_routes(create_app()) == []


def test_the_walk_catches_an_unmarked_route() -> None:
    application = FastAPI()

    @application.get("/forgotten")
    def forgotten() -> dict[str, str]:
        return {"status": "open"}

    @application.get("/open")
    @public
    def open_route() -> dict[str, str]:
        return {"status": "open"}

    assert unmarked_routes(application) == ["/forgotten"]


def unmarked_routes(application: FastAPI) -> list[str]:
    found: list[str] = []
    for route in iter_api_routes(application):
        if getattr(route.endpoint, "is_public", False):
            continue
        if any(getattr(dep.call, "allowed_roles", None) for dep in route.dependant.dependencies):
            continue
        found.append(route.path)
    return sorted(found)


def iter_api_routes(application: FastAPI) -> Iterator[APIRoute]:
    """Routes declared on the app, including ones added with include_router.

    This FastAPI version stores included routers as one object instead of copying
    each route onto the app, so a walk of app.routes alone would miss them.
    """
    yield from _walk_routes(application.routes)


def _walk_routes(routes: Iterable[object]) -> Iterator[APIRoute]:
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _walk_routes(original.routes)


def _login(client: TestClient, email: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": _PASSWORD})
    assert response.status_code == 200
    return str(response.cookies["dc_session"])
