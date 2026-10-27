"""Shared pytest fixtures for every Python package in the workspace.

Database tests run against a real Postgres + pgvector instance named by
``CARD_MAVEN_TEST_DATABASE_URL`` (CI provides one; locally ``make up`` does).
The schema is built once per session by running the Alembic migrations, so
every test run also exercises the migrations. Each test runs inside a
transaction that is rolled back afterwards.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from card_maven.catalog.reference_data import load_reference_data, seed_reference_data
from card_maven.shared.db import make_engine

REPO_ROOT = Path(__file__).resolve().parent
TEST_DB_ENV = "CARD_MAVEN_TEST_DATABASE_URL"


def _test_database_url() -> str:
    url = os.environ.get(TEST_DB_ENV)
    if not url:
        pytest.skip(f"{TEST_DB_ENV} is not set; database tests need Postgres (run `make up`)")
    if "test" not in url.rsplit("/", 1)[-1]:
        # Tests truncate tables. Refuse to run against a non-test database.
        pytest.fail(f"{TEST_DB_ENV} must point at a database whose name contains 'test'")
    return url


def alembic_config(url: str) -> Config:
    config = Config(str(REPO_ROOT / "db" / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "db" / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    return _test_database_url()


@pytest.fixture(scope="session")
def alembic_cfg(database_url: str) -> Config:
    return alembic_config(database_url)


@pytest.fixture(scope="session")
def engine(database_url: str, alembic_cfg: Config) -> Iterator[Engine]:
    config = alembic_cfg
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = make_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after the test, even if it commits."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def committing_session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """Real commits, for tests that need several connections (e.g. row locking).

    Tables are truncated afterwards. Use only when ``db_session`` can't work.
    """
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    with engine.begin() as connection:
        tables = connection.execute(
            text(
                "SELECT string_agg(quote_ident(tablename), ', ') FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).scalar_one()
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def seeded_session(db_session: Session) -> Session:
    """A rolled-back session with sports and brands from the real reference file."""
    seed_reference_data(
        db_session, load_reference_data(REPO_ROOT / "config" / "reference_data.yaml")
    )
    return db_session
