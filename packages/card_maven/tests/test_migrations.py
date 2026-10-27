"""The migrations are the schema's source of truth in every environment."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from card_maven.models import Base

pytestmark = pytest.mark.db


def test_models_match_migrations(engine: Engine) -> None:
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], f"models and migrations differ; run `make migration`: {diff}"


def test_downgrade_and_upgrade_round_trip(engine: Engine, alembic_cfg: Config) -> None:
    command.downgrade(alembic_cfg, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(alembic_cfg, "head")
    assert {"collection_item", "card_variant", "outbox_message"} <= set(
        inspect(engine).get_table_names()
    )
