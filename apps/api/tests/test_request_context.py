import logging

import pytest
from fastapi.testclient import TestClient

from dentacircle.main import create_app


def test_request_id_is_generated_and_ignores_the_client(client: TestClient) -> None:
    first = client.get("/health", headers={"X-Request-ID": "client-sent"})
    second = client.get("/health", headers={"X-Request-ID": "client-sent"})
    first_id = first.headers["X-Request-ID"]
    second_id = second.headers["X-Request-ID"]
    assert first_id != "client-sent"
    assert second_id != "client-sent"
    assert first_id != second_id


def test_request_log_has_no_query_string(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="dentacircle.request")
    response = client.get("/health", params={"patient": "synthetic-name"})
    records = [record for record in caplog.records if record.name == "dentacircle.request"]
    assert response.status_code == 200
    assert len(records) == 1
    message = records[0].getMessage()
    assert f"request_id={response.headers['X-Request-ID']}" in message
    assert "method=GET" in message
    assert "path=/health" in message
    assert "status=200" in message
    assert "duration_ms=" in message
    assert "synthetic-name" not in message
    assert "patient=" not in message
    assert "?" not in message


def test_unhandled_exception_log_omits_the_message_unless_debug(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    application = create_app()

    @application.get("/explode")
    def explode() -> None:
        raise RuntimeError("synthetic-marker")

    caplog.set_level(logging.INFO)
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/explode")
    assert response.status_code == 500
    assert "RuntimeError" in caplog.text
    assert "synthetic-marker" not in caplog.text
    assert "Traceback" not in caplog.text


def test_debug_log_includes_the_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    application = create_app()

    @application.get("/explode")
    def explode() -> None:
        raise RuntimeError("synthetic-marker")

    caplog.set_level(logging.DEBUG)
    with TestClient(application, raise_server_exceptions=False) as client:
        client.get("/explode")
    assert "Traceback" in caplog.text
    assert "RuntimeError" in caplog.text
