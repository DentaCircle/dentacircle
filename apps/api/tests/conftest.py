"""Shared API client and database fixtures."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from dentacircle.core.database import clear_engine
from dentacircle.main import create_app
from tests.support import create_throwaway_database, drop_database, rollback_session


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr("dentacircle.core.config.env_file", lambda: None)
    clear_engine()
    yield
    clear_engine()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def throwaway_database_url() -> Iterator[str]:
    database_url = os.environ.get("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is not set")
    created = create_throwaway_database(database_url)
    try:
        yield created
    finally:
        clear_engine()
        drop_database(created)


@pytest.fixture
def db_session(throwaway_database_url: str) -> Iterator[Session]:
    with rollback_session(throwaway_database_url) as session:
        yield session
