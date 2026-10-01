import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from dentacircle.main import create_app


def test_unknown_route_uses_the_error_shape(client: TestClient) -> None:
    response = client.get("/missing")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == "not_found"
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]


def test_wrong_method_uses_the_error_shape(client: TestClient) -> None:
    response = client.post("/health")
    assert response.status_code == 405
    body = response.json()["error"]
    assert body["code"] == "method_not_allowed"
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_http_exception_uses_the_error_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    application = create_app()

    @application.get("/denied")
    def denied() -> None:
        raise HTTPException(status_code=400, detail="Bad request")

    with TestClient(application) as client:
        response = client.get("/denied")
    body = response.json()
    assert response.status_code == 400
    assert set(body) == {"error"}
    assert body["error"]["code"] == "bad_request"
    assert body["error"]["message"] == "Bad request"
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]


def test_validation_error_lists_location_and_rule_without_the_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    application = create_app()

    @application.get("/needs-int")
    def needs_int(count: int) -> dict[str, int]:
        return {"count": count}

    with TestClient(application) as client:
        response = client.get("/needs-int", params={"count": "synthetic-bad-value"})
    body = response.json()
    assert response.status_code == 422
    assert set(body) == {"error"}
    assert body["error"]["code"] == "validation_error"
    assert "query.count" in body["error"]["message"]
    assert "int_parsing" in body["error"]["message"]
    assert "synthetic-bad-value" not in response.text
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]


def test_unhandled_exception_hides_the_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    application = create_app()

    @application.get("/explode")
    def explode() -> None:
        raise RuntimeError("synthetic-marker")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/explode")
    body = response.json()
    assert response.status_code == 500
    assert set(body) == {"error"}
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "Something went wrong."
    assert "synthetic-marker" not in response.text
    assert "RuntimeError" not in response.text
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]
