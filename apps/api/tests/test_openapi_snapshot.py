"""The committed OpenAPI file must match the running app."""

import json
from pathlib import Path

import pytest

from dentacircle.main import create_app


def test_committed_openapi_matches_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    path = Path(__file__).resolve().parents[1] / "openapi.json"
    committed = json.loads(path.read_text())
    assert create_app().openapi() == committed
