"""Database helpers shared by the test harness."""

from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dentacircle.core.database import to_psycopg_url, to_sqlalchemy_url


def create_throwaway_database(database_url: str) -> str:
    name = f"dentacircle_test_{uuid4().hex}"
    admin_url = to_psycopg_url(_with_database(database_url, "postgres"))
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=5) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return _with_database(database_url, name)


def drop_database(database_url: str) -> None:
    name = urlsplit(database_url).path.lstrip("/")
    admin_url = to_psycopg_url(_with_database(database_url, "postgres"))
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=5) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (name,),
        )
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


@contextmanager
def rollback_session(database_url: str) -> Iterator[Session]:
    """A session whose commit is undone when the context exits."""
    engine = create_engine(to_sqlalchemy_url(database_url), connect_args={"connect_timeout": 5})
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def _with_database(database_url: str, name: str) -> str:
    parts = urlsplit(database_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
