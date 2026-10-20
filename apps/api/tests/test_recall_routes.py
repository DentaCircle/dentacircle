"""Recall routes name their roles, and a route with none is refused."""

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from dentacircle.domain.recall import RECALL_ROLES
from dentacircle.main import create_app
from tests.test_access import iter_api_routes, unmarked_routes


def test_recall_routes_declare_their_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    application = create_app()
    assert unmarked_routes(application) == []
    found = _route_roles(application)
    assert found[("GET", "/recalls")] == set(RECALL_ROLES)
    assert found[("GET", "/recalls/{recall_id}")] == set(RECALL_ROLES)
    assert found[("POST", "/recalls/{recall_id}/contacted")] == set(RECALL_ROLES)
    assert found[("POST", "/recalls/{recall_id}/book")] == set(RECALL_ROLES)
    assert found[("POST", "/recalls/{recall_id}/cancel")] == set(RECALL_ROLES)


def _route_roles(application: FastAPI) -> dict[tuple[str, str], set[str]]:
    found: dict[tuple[str, str], set[str]] = {}
    for route in iter_api_routes(application):
        if not isinstance(route, APIRoute):
            continue
        allowed: set[str] = set()
        for dep in route.dependant.dependencies:
            roles = getattr(dep.call, "allowed_roles", None)
            if roles:
                allowed.update(roles)
        for method in route.methods or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            found[(method, route.path)] = allowed
    return found
