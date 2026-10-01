from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).resolve().parents[1]


def test_baseline_upgrade_and_downgrade(
    throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))

    command.upgrade(config, "head")
    assert _public_tables(throwaway_database_url) == ["alembic_version"]
    assert _version(throwaway_database_url) == _head(config)

    command.downgrade(config, "base")
    assert _versions(throwaway_database_url) == []

    command.upgrade(config, "head")
    assert _public_tables(throwaway_database_url) == ["alembic_version"]
    assert _version(throwaway_database_url) == "0001_baseline"


def _public_tables(database_url: str) -> list[str]:
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        ).fetchall()
    return [row[0] for row in rows]


def _version(database_url: str) -> str:
    versions = _versions(database_url)
    assert len(versions) == 1
    return versions[0]


def _versions(database_url: str) -> list[str]:
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    return [str(row[0]) for row in rows]


def _head(config: Config) -> str:
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head
