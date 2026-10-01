"""Sync SQLAlchemy engine. Async is intentionally not used. See PRODUCT.md."""

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

from dentacircle.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_engine: Engine | None = None


def to_sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    raise ValueError("DATABASE_URL must start with postgresql://")


def alembic_sqlalchemy_url(database_url: str) -> str:
    # ConfigParser treats % as interpolation. Escape it before Alembic stores the URL.
    return to_sqlalchemy_url(database_url).replace("%", "%%")


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            to_sqlalchemy_url(get_settings().database_url),
            connect_args={"connect_timeout": 5},
        )
    return _engine


def clear_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def get_session() -> Iterator[Session]:
    session = Session(get_engine())
    try:
        yield session
    finally:
        session.close()
