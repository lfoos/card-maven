"""Market data: sources, sales, listings, sync jobs, idempotency, taxonomy terms.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27 18:44:20.833447
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_term",
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("aspect", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("source", "aspect", "value", name=op.f("pk_catalog_term")),
    )
    op.create_table(
        "market_source",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("license", sa.String(length=16), nullable=False),
        sa.Column("max_age_hours", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "license = 'analytics' OR max_age_hours IS NOT NULL",
            name=op.f("ck_market_source_display_only_has_max_age"),
        ),
        sa.CheckConstraint(
            "license IN ('analytics', 'display_only')", name=op.f("ck_market_source_license_valid")
        ),
        sa.CheckConstraint(
            "max_age_hours IS NULL OR max_age_hours > 0",
            name=op.f("ck_market_source_max_age_positive"),
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_market_source")),
    )
    op.create_table(
        "processed_event",
        sa.Column("consumer", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("consumer", "event_id", name=op.f("pk_processed_event")),
    )
    op.create_table(
        "market_sync_job",
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name=op.f("ck_market_sync_job_status_valid"),
        ),
        sa.CheckConstraint(
            "target_type IN ('variant', 'tracked_set')",
            name=op.f("ck_market_sync_job_target_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["app_user.id"],
            name=op.f("fk_market_sync_job_requested_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_sync_job")),
    )
    op.create_index(
        "ix_market_sync_job_target",
        "market_sync_job",
        ["target_type", "target_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "listing",
        sa.Column("buying_option", sa.String(length=16), nullable=False),
        sa.Column("bid_count", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.String(length=2000), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("source_listing_id", sa.String(length=128), nullable=False),
        sa.Column("match_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("match_method", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("price_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("condition", sa.String(length=16), nullable=False),
        sa.Column("grader", sa.String(length=16), nullable=True),
        sa.Column("grade", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("source_code", sa.String(length=32), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(condition = 'graded' AND grader IS NOT NULL AND grade IS NOT NULL) OR (condition = 'raw' AND grader IS NULL AND grade IS NULL)",
            name=op.f("ck_listing_grade_matches_condition"),
        ),
        sa.CheckConstraint(
            "buying_option IN ('auction', 'fixed_price', 'best_offer', 'other')",
            name=op.f("ck_listing_buying_option_valid"),
        ),
        sa.CheckConstraint(
            "condition IN ('raw', 'graded')", name=op.f("ck_listing_condition_valid")
        ),
        sa.CheckConstraint(
            "(variant_id IS NULL) = (match_confidence IS NULL)",
            name=op.f("ck_listing_match_has_confidence"),
        ),
        sa.CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name=op.f("ck_listing_confidence_range"),
        ),
        sa.CheckConstraint("price_minor >= 0", name=op.f("ck_listing_price_non_negative")),
        sa.CheckConstraint("variant_id IS NOT NULL", name=op.f("ck_listing_listing_is_matched")),
        sa.ForeignKeyConstraint(
            ["source_code"],
            ["market_source.code"],
            name=op.f("fk_listing_source_code_market_source"),
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["card_variant.id"],
            name=op.f("fk_listing_variant_id_card_variant"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_listing")),
        sa.UniqueConstraint(
            "source_code",
            "source_listing_id",
            name=op.f("uq_listing_source_code_source_listing_id"),
        ),
    )
    op.create_index("ix_listing_observed_at", "listing", ["observed_at"], unique=False)
    op.create_index(
        "ix_listing_variant_recent",
        "listing",
        ["variant_id", sa.literal_column("observed_at DESC")],
        unique=False,
    )
    op.create_table(
        "sale",
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sale_type", sa.String(length=16), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
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
        sa.Column("source_listing_id", sa.String(length=128), nullable=False),
        sa.Column("match_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("match_method", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("price_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("condition", sa.String(length=16), nullable=False),
        sa.Column("grader", sa.String(length=16), nullable=True),
        sa.Column("grade", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("source_code", sa.String(length=32), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(condition = 'graded' AND grader IS NOT NULL AND grade IS NOT NULL) OR (condition = 'raw' AND grader IS NULL AND grade IS NULL)",
            name=op.f("ck_sale_grade_matches_condition"),
        ),
        sa.CheckConstraint("condition IN ('raw', 'graded')", name=op.f("ck_sale_condition_valid")),
        sa.CheckConstraint(
            "sale_type IN ('auction', 'fixed_price', 'best_offer', 'other')",
            name=op.f("ck_sale_sale_type_valid"),
        ),
        sa.CheckConstraint(
            "(variant_id IS NULL) = (match_confidence IS NULL)",
            name=op.f("ck_sale_match_has_confidence"),
        ),
        sa.CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name=op.f("ck_sale_confidence_range"),
        ),
        sa.CheckConstraint("price_minor >= 0", name=op.f("ck_sale_price_non_negative")),
        sa.ForeignKeyConstraint(
            ["source_code"], ["market_source.code"], name=op.f("fk_sale_source_code_market_source")
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["app_user.id"],
            name=op.f("fk_sale_submitted_by_app_user"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["card_variant.id"],
            name=op.f("fk_sale_variant_id_card_variant"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale")),
        sa.UniqueConstraint(
            "source_code", "source_listing_id", name=op.f("uq_sale_source_code_source_listing_id")
        ),
    )
    op.create_index(op.f("ix_sale_submitted_by"), "sale", ["submitted_by"], unique=False)
    op.create_index(
        "ix_sale_variant_recent",
        "sale",
        ["variant_id", sa.literal_column("sold_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sale_variant_recent", table_name="sale")
    op.drop_index(op.f("ix_sale_submitted_by"), table_name="sale")
    op.drop_table("sale")
    op.drop_index("ix_listing_variant_recent", table_name="listing")
    op.drop_index("ix_listing_observed_at", table_name="listing")
    op.drop_table("listing")
    op.drop_index("ix_market_sync_job_target", table_name="market_sync_job")
    op.drop_table("market_sync_job")
    op.drop_table("processed_event")
    op.drop_table("market_source")
    op.drop_table("catalog_term")
