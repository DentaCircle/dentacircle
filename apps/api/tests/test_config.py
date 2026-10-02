import pytest

from dentacircle.core.config import StartupError, get_settings
from dentacircle.core.database import to_psycopg_url, to_sqlalchemy_url
from dentacircle.main import create_app


def test_app_refuses_to_start_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(StartupError) as caught:
        create_app()
    assert "DATABASE_URL" in str(caught.value)


def test_settings_default_log_level_is_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert get_settings().log_level == "INFO"


def test_invalid_log_level_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    with pytest.raises(StartupError) as caught:
        get_settings()
    assert "LOG_LEVEL" in str(caught.value)


def test_log_level_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://dentacircle:dentacircle@127.0.0.1:5432/dentacircle",
    )
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert get_settings().log_level == "DEBUG"


def test_postgres_scheme_is_normalized_for_sqlalchemy() -> None:
    assert (
        to_sqlalchemy_url("postgresql://dentacircle:dentacircle@localhost:5432/dentacircle")
        == "postgresql+psycopg://dentacircle:dentacircle@localhost:5432/dentacircle"
    )
    assert (
        to_sqlalchemy_url("postgres://dentacircle:dentacircle@localhost:5432/dentacircle")
        == "postgresql+psycopg://dentacircle:dentacircle@localhost:5432/dentacircle"
    )


def test_sqlalchemy_scheme_is_left_unchanged() -> None:
    url = "postgresql+psycopg://dentacircle:dentacircle@localhost:5432/dentacircle"
    assert to_sqlalchemy_url(url) == url


def test_psycopg_url_strips_the_sqlalchemy_driver() -> None:
    assert (
        to_psycopg_url("postgresql+psycopg://dentacircle:dentacircle@localhost:5432/dentacircle")
        == "postgresql://dentacircle:dentacircle@localhost:5432/dentacircle"
    )
    assert (
        to_psycopg_url("postgres://dentacircle:dentacircle@localhost:5432/dentacircle")
        == "postgresql://dentacircle:dentacircle@localhost:5432/dentacircle"
    )
    plain = "postgresql://dentacircle:dentacircle@localhost:5432/dentacircle"
    assert to_psycopg_url(plain) == plain
