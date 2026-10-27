"""Collection: image lifecycle, case-insensitive natural keys, search indexes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26 22:26:19.033426
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Trigram indexes back ILIKE search and autocomplete.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.drop_constraint(op.f("uq_card_set_id_card_number"), "card", type_="unique")
    op.create_index(
        "ix_card_name_trgm",
        "card",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "uq_card_set_number",
        "card",
        ["set_id", sa.literal_column("upper(card_number)")],
        unique=True,
    )
    op.drop_constraint(
        op.f("uq_card_set_sport_code_brand_slug_year_name"), "card_set", type_="unique"
    )
    op.create_index(
        "ix_card_set_name_trgm",
        "card_set",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "uq_card_set_natural_key",
        "card_set",
        ["sport_code", "brand_slug", "year", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_index(
        "ix_collection_item_owner_recent",
        "collection_item",
        ["owner_id", sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.add_column(
        "image", sa.Column("status", sa.String(length=16), server_default="pending", nullable=False)
    )
    op.add_column("image", sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        op.f("ck_image_status_valid"), "image", "status IN ('pending', 'ready')"
    )
    op.create_index(
        "uq_image_live_side",
        "image",
        ["collection_item_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'ready' AND kind IN ('front', 'back')"),
    )
    op.drop_constraint(op.f("uq_parallel_set_id_subset_name"), "parallel", type_="unique")
    op.create_index(
        "uq_parallel_natural_key",
        "parallel",
        ["set_id", sa.literal_column("coalesce(subset, '')"), sa.literal_column("lower(name)")],
        unique=True,
    )
    op.drop_index(op.f("ix_player_full_name"), table_name="player")
    op.create_index(
        "ix_player_full_name_trgm",
        "player",
        ["full_name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"full_name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_player_sport_name",
        "player",
        ["sport_code", sa.literal_column("lower(full_name)")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_player_sport_name", table_name="player")
    op.drop_index(
        "ix_player_full_name_trgm",
        table_name="player",
        postgresql_using="gin",
        postgresql_ops={"full_name": "gin_trgm_ops"},
    )
    op.create_index(op.f("ix_player_full_name"), "player", ["full_name"], unique=False)
    op.drop_index("uq_parallel_natural_key", table_name="parallel")
    op.create_unique_constraint(
        op.f("uq_parallel_set_id_subset_name"),
        "parallel",
        ["set_id", "subset", "name"],
        postgresql_nulls_not_distinct=True,
    )
    op.drop_index(
        "uq_image_live_side",
        table_name="image",
        postgresql_where=sa.text("status = 'ready' AND kind IN ('front', 'back')"),
    )
    op.drop_constraint(op.f("ck_image_status_valid"), "image", type_="check")
    op.drop_column("image", "uploaded_at")
    op.drop_column("image", "status")
    op.drop_index("ix_collection_item_owner_recent", table_name="collection_item")
    op.drop_index("uq_card_set_natural_key", table_name="card_set")
    op.drop_index(
        "ix_card_set_name_trgm",
        table_name="card_set",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_unique_constraint(
        op.f("uq_card_set_sport_code_brand_slug_year_name"),
        "card_set",
        ["sport_code", "brand_slug", "year", "name"],
        postgresql_nulls_not_distinct=False,
    )
    op.drop_index("uq_card_set_number", table_name="card")
    op.drop_index(
        "ix_card_name_trgm",
        table_name="card",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_unique_constraint(
        op.f("uq_card_set_id_card_number"),
        "card",
        ["set_id", "card_number"],
        postgresql_nulls_not_distinct=False,
    )
    # pg_trgm is left installed; other objects may use it.
