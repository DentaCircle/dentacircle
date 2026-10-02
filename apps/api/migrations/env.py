"""Alembic environment. The database URL is the same DATABASE_URL the API uses."""

from alembic import context
from sqlalchemy import engine_from_config, pool

from dentacircle.core.config import get_settings
from dentacircle.core.database import Base, alembic_sqlalchemy_url

config = context.config
config.set_main_option("sqlalchemy.url", alembic_sqlalchemy_url(get_settings().database_url))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
