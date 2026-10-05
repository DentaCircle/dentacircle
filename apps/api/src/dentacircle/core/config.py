"""Environment settings. The API will not start without DATABASE_URL."""

from pathlib import Path

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_POSTGRES_PREFIXES = ("postgresql://", "postgres://", "postgresql+psycopg://")


class StartupError(Exception):
    """Raised when configuration is missing or invalid."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    log_level: str = "INFO"
    session_ttl_hours: int = 12
    cookie_secure: bool = True

    @field_validator("database_url")
    @classmethod
    def database_url_must_be_postgres(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("DATABASE_URL is missing")
        if value.startswith(_POSTGRES_PREFIXES):
            return value
        raise ValueError("DATABASE_URL must start with postgresql://")

    @field_validator("log_level", mode="before")
    @classmethod
    def log_level_must_be_known(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.upper()
        if normalized not in _LOG_LEVELS:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        return normalized

    @field_validator("session_ttl_hours")
    @classmethod
    def session_ttl_must_be_positive(cls, value: int) -> int:
        if value >= 1:
            return value
        raise ValueError("SESSION_TTL_HOURS must be a positive integer")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "Makefile").is_file() and (parent / "apps" / "api").is_dir():
            return parent
    raise StartupError("Could not find the repository root from the API package")


def env_file() -> Path | None:
    path = repo_root() / ".env"
    if path.is_file():
        return path
    return None


def get_settings() -> Settings:
    try:
        return Settings(_env_file=env_file())
    except ValidationError as exc:
        raise StartupError(_startup_message(exc)) from exc


def _startup_message(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        if error["loc"] == ("database_url",):
            if error["type"] == "missing":
                parts.append("DATABASE_URL is missing")
            else:
                parts.append(str(error["msg"]))
        elif error["loc"] == ("log_level",):
            parts.append("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        elif error["loc"] == ("session_ttl_hours",):
            parts.append("SESSION_TTL_HOURS must be a positive integer")
        elif error["loc"] == ("cookie_secure",):
            parts.append("COOKIE_SECURE must be true or false")
        else:
            parts.append(str(error["msg"]))
    return "; ".join(parts)
