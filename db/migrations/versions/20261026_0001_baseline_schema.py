"""Baseline schema: identity, catalog, collection, tracked sets, outbox.

Revision ID: 0001
Revises:
Create Date: 2026-10-26 21:00:38.360226
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector: embeddings arrive in Phase 3; the extension is enabled up front.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "app_user",
        sa.Column("idp_issuer", sa.String(length=500), nullable=False),
        sa.Column("idp_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
        sa.UniqueConstraint(
            "idp_issuer", "idp_subject", name=op.f("uq_app_user_idp_issuer_idp_subject")
        ),
    )
    op.create_table(
        "brand",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("slug", name=op.f("pk_brand")),
        sa.UniqueConstraint("name", name=op.f("uq_brand_name")),
    )
    op.create_table(
        "outbox_message",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("partition_key", sa.String(length=200), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_message")),
        sa.UniqueConstraint("event_id", name=op.f("uq_outbox_message_event_id")),
    )
    op.create_index(
        "ix_outbox_message_pending",
        "outbox_message",
        ["available_at", "id"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_table(
        "sport",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_sport")),
        sa.UniqueConstraint("name", name=op.f("uq_sport_name")),
    )
    op.create_table(
        "card_set",
        sa.Column("sport_code", sa.String(length=32), nullable=False),
        sa.Column("brand_slug", sa.String(length=64), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "catalog_source", sa.String(length=64), server_default="user_confirmed", nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("year BETWEEN 1860 AND 2100", name=op.f("ck_card_set_year_range")),
        sa.ForeignKeyConstraint(
            ["brand_slug"], ["brand.slug"], name=op.f("fk_card_set_brand_slug_brand")
        ),
        sa.ForeignKeyConstraint(
            ["sport_code"], ["sport.code"], name=op.f("fk_card_set_sport_code_sport")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_card_set")),
        sa.UniqueConstraint(
            "sport_code",
            "brand_slug",
            "year",
            "name",
            name=op.f("uq_card_set_sport_code_brand_slug_year_name"),
        ),
    )
    op.create_table(
        "player",
        sa.Column("sport_code", sa.String(length=32), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column(
            "external_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sport_code"], ["sport.code"], name=op.f("fk_player_sport_code_sport")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player")),
    )
    op.create_index(op.f("ix_player_full_name"), "player", ["full_name"], unique=False)
    op.create_table(
        "tracked_set",
        sa.Column("sport_code", sa.String(length=32), nullable=False),
        sa.Column("brand_slug", sa.String(length=64), nullable=False),
        sa.Column("set_name", sa.String(length=200), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("focus", sa.String(length=200), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("year BETWEEN 1860 AND 2100", name=op.f("ck_tracked_set_year_range")),
        sa.ForeignKeyConstraint(
            ["brand_slug"], ["brand.slug"], name=op.f("fk_tracked_set_brand_slug_brand")
        ),
        sa.ForeignKeyConstraint(
            ["sport_code"], ["sport.code"], name=op.f("fk_tracked_set_sport_code_sport")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracked_set")),
        sa.UniqueConstraint(
            "sport_code",
            "brand_slug",
            "set_name",
            "year",
            name=op.f("uq_tracked_set_sport_code_brand_slug_set_name_year"),
        ),
    )
    op.create_table(
        "card",
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("card_number", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("subset", sa.String(length=200), nullable=True),
        sa.Column("team", sa.String(length=200), nullable=True),
        sa.Column("is_rookie", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_autograph", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_memorabilia", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "catalog_source", sa.String(length=64), server_default="user_confirmed", nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["set_id"], ["card_set.id"], name=op.f("fk_card_set_id_card_set"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_card")),
        sa.UniqueConstraint("set_id", "card_number", name=op.f("uq_card_set_id_card_number")),
    )
    op.create_table(
        "parallel",
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("subset", sa.String(length=200), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("color", sa.String(length=64), nullable=True),
        sa.Column("print_run", sa.Integer(), nullable=True),
        sa.Column(
            "catalog_source", sa.String(length=64), server_default="user_confirmed", nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "print_run IS NULL OR print_run > 0", name=op.f("ck_parallel_print_run_positive")
        ),
        sa.ForeignKeyConstraint(
            ["set_id"],
            ["card_set.id"],
            name=op.f("fk_parallel_set_id_card_set"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parallel")),
        sa.UniqueConstraint(
            "set_id",
            "subset",
            "name",
            name=op.f("uq_parallel_set_id_subset_name"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_table(
        "card_player",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["card_id"], ["card.id"], name=op.f("fk_card_player_card_id_card"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["player.id"],
            name=op.f("fk_card_player_player_id_player"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("card_id", "player_id", name=op.f("pk_card_player")),
    )
    op.create_index(op.f("ix_card_player_player_id"), "card_player", ["player_id"], unique=False)
    op.create_table(
        "card_variant",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("parallel_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["card.id"], name=op.f("fk_card_variant_card_id_card"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parallel_id"],
            ["parallel.id"],
            name=op.f("fk_card_variant_parallel_id_parallel"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_card_variant")),
        sa.UniqueConstraint(
            "card_id", "parallel_id", name=op.f("uq_card_variant_card_id_parallel_id")
        ),
    )
    op.create_index(
        op.f("ix_card_variant_parallel_id"), "card_variant", ["parallel_id"], unique=False
    )
    op.create_table(
        "collection_item",
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=True),
        sa.Column("condition", sa.String(length=16), server_default="raw", nullable=False),
        sa.Column("grader", sa.String(length=16), nullable=True),
        sa.Column("grade", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("cert_number", sa.String(length=64), nullable=True),
        sa.Column("purchase_price_minor", sa.BigInteger(), nullable=True),
        sa.Column("purchase_currency", sa.String(length=3), nullable=True),
        sa.Column("acquired_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(condition = 'graded' AND grader IS NOT NULL AND grade IS NOT NULL) OR (condition = 'raw' AND grader IS NULL AND grade IS NULL AND cert_number IS NULL)",
            name=op.f("ck_collection_item_grade_matches_condition"),
        ),
        sa.CheckConstraint(
            "condition IN ('raw', 'graded')", name=op.f("ck_collection_item_condition_valid")
        ),
        sa.CheckConstraint(
            "(purchase_price_minor IS NULL) = (purchase_currency IS NULL)",
            name=op.f("ck_collection_item_purchase_price_has_currency"),
        ),
        sa.CheckConstraint(
            "grade IS NULL OR (grade >= 1 AND grade <= 10)",
            name=op.f("ck_collection_item_grade_range"),
        ),
        sa.CheckConstraint(
            "purchase_price_minor IS NULL OR purchase_price_minor >= 0",
            name=op.f("ck_collection_item_purchase_price_non_negative"),
        ),
        sa.CheckConstraint(
            "serial_number IS NULL OR serial_number > 0",
            name=op.f("ck_collection_item_serial_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["app_user.id"],
            name=op.f("fk_collection_item_owner_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["card_variant.id"],
            name=op.f("fk_collection_item_variant_id_card_variant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_item")),
    )
    op.create_index(
        op.f("ix_collection_item_owner_id"), "collection_item", ["owner_id"], unique=False
    )
    op.create_index(
        op.f("ix_collection_item_variant_id"), "collection_item", ["variant_id"], unique=False
    )
    op.create_table(
        "image",
        sa.Column("collection_item_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('front', 'back', 'scan_source', 'crop')", name=op.f("ck_image_kind_valid")
        ),
        sa.CheckConstraint("byte_size > 0", name=op.f("ck_image_byte_size_positive")),
        sa.ForeignKeyConstraint(
            ["collection_item_id"],
            ["collection_item.id"],
            name=op.f("fk_image_collection_item_id_collection_item"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["app_user.id"],
            name=op.f("fk_image_owner_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_image")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_image_storage_key")),
    )
    op.create_index(
        op.f("ix_image_collection_item_id"), "image", ["collection_item_id"], unique=False
    )
    op.create_index(op.f("ix_image_owner_id"), "image", ["owner_id"], unique=False)
    op.create_index(op.f("ix_image_sha256"), "image", ["sha256"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_image_sha256"), table_name="image")
    op.drop_index(op.f("ix_image_owner_id"), table_name="image")
    op.drop_index(op.f("ix_image_collection_item_id"), table_name="image")
    op.drop_table("image")
    op.drop_index(op.f("ix_collection_item_variant_id"), table_name="collection_item")
    op.drop_index(op.f("ix_collection_item_owner_id"), table_name="collection_item")
    op.drop_table("collection_item")
    op.drop_index(op.f("ix_card_variant_parallel_id"), table_name="card_variant")
    op.drop_table("card_variant")
    op.drop_index(op.f("ix_card_player_player_id"), table_name="card_player")
    op.drop_table("card_player")
    op.drop_table("parallel")
    op.drop_table("card")
    op.drop_table("tracked_set")
    op.drop_index(op.f("ix_player_full_name"), table_name="player")
    op.drop_table("player")
    op.drop_table("card_set")
    op.drop_table("sport")
    op.drop_index(
        "ix_outbox_message_pending",
        table_name="outbox_message",
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.drop_table("outbox_message")
    op.drop_table("brand")
    op.drop_table("app_user")
    # The vector extension is left installed; other databases objects may use it.
