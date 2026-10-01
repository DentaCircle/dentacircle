import os

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dentacircle.core.database import to_sqlalchemy_url
from dentacircle.main import create_app
from dentacircle.services.health_service import DatabaseNotReady, database_is_ready


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_does_not_touch_the_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail() -> object:
        raise AssertionError("database engine was created")

    monkeypatch.setattr("dentacircle.core.database.get_engine", fail)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_routes_are_public(client: TestClient) -> None:
    application = client.app
    assert isinstance(application, FastAPI)
    paths = sorted(
        route.path
        for route in _api_routes(application)
        if getattr(route.endpoint, "is_public", False)
    )
    assert paths == ["/health", "/health/ready"]


def _api_routes(application: FastAPI) -> list[APIRoute]:
    found: list[APIRoute] = []
    for route in application.routes:
        if isinstance(route, APIRoute):
            found.append(route)
        original = getattr(route, "original_router", None)
        if original is None:
            continue
        found.extend(item for item in original.routes if isinstance(item, APIRoute))
    return found


def test_readiness_returns_ok_when_database_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is not set")
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_503_when_database_is_down(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:synthetic-secret-pw@127.0.0.1:1/dentacircle",
    )
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    caplog.set_level("INFO")
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()["error"]
    assert body["code"] == "service_unavailable"
    assert body["message"] == "Database is not ready."
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert "synthetic-secret-pw" not in response.text
    assert "synthetic-secret-pw" not in caplog.text
    assert "exception_class=" in caplog.text


def test_database_is_ready_runs_select_one(db_session: Session) -> None:
    database_is_ready(db_session, "req-1")


def test_database_is_ready_hides_the_driver_message(caplog: pytest.LogCaptureFixture) -> None:
    engine = create_engine(
        to_sqlalchemy_url("postgresql://dentacircle:synthetic-secret-pw@127.0.0.1:1/dentacircle"),
        connect_args={"connect_timeout": 5},
    )
    session = Session(engine)
    caplog.set_level("INFO")
    try:
        with pytest.raises(DatabaseNotReady) as caught:
            database_is_ready(session, "req-1")
    finally:
        session.close()
        engine.dispose()
    assert str(caught.value) == ""
    assert "request_id=req-1" in caplog.text
    assert "synthetic-secret-pw" not in caplog.text
