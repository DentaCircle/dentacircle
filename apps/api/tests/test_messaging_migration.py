"""The additive messaging migration can be applied and rolled back."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from dentacircle.core.database import to_sqlalchemy_url


def test_messaging_migration(throwaway_database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", throwaway_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(to_sqlalchemy_url(throwaway_database_url))
    try:
        inspector = inspect(engine)
        assert {"messaging_contact", "message"}.issubset(inspector.get_table_names())
        assert len(inspector.get_foreign_keys("message")) == 3
        assert len(inspector.get_unique_constraints("message")) == 2
        command.downgrade(config, "0020_procedure_resource_rules")
        assert "message" not in inspect(engine).get_table_names()
        assert "messaging_contact" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
