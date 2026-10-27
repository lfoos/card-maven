"""Alembic environment. Uses the application's settings and model metadata."""

from __future__ import annotations

from alembic import context
from sqlalchemy import pool

from card_maven.models import Base
from card_maven.shared.config import Settings
from card_maven.shared.db import make_engine

target_metadata = Base.metadata


def _database_url() -> str:
    # An explicit URL (used by tests) wins over environment settings.
    override = context.config.get_main_option("sqlalchemy.url")
    return override or Settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
