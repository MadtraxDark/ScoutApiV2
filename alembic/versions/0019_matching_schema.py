"""Initial matching schema: canonical products, listings, offer history."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_matching_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canonical_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("variant_key", sa.String(length=256), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "product_identifiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_product_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("value_normalized", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["canonical_product_id"],
            ["canonical_products.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "type", "value_normalized", name="uq_product_identifiers_type_value"
        ),
    )
    op.create_index(
        "ix_product_identifiers_canonical",
        "product_identifiers",
        ["canonical_product_id"],
    )
    op.create_table(
        "store_listings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_product_id", sa.Uuid(), nullable=False),
        sa.Column("store", sa.String(length=64), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("product_id", sa.String(length=128), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=True),
        sa.Column("gtin", sa.String(length=32), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("match_decision", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["canonical_product_id"],
            ["canonical_products.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store", "canonical_url", name="uq_store_listings_store_url"
        ),
    )
    op.create_index(
        "ix_store_listings_canonical_product",
        "store_listings",
        ["canonical_product_id"],
    )
    op.create_index("ix_store_listings_gtin", "store_listings", ["gtin"])
    op.create_table(
        "offer_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("seller", sa.String(length=256), nullable=True),
        sa.Column("availability", sa.String(length=32), nullable=True),
        sa.Column("available", sa.Boolean(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["store_listings.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_offer_snapshots_listing_scraped",
        "offer_snapshots",
        ["listing_id", "scraped_at"],
    )
    op.create_table(
        "offer_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["store_listings.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_offer_events_listing_detected",
        "offer_events",
        ["listing_id", "detected_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_offer_events_listing_detected", table_name="offer_events")
    op.drop_table("offer_events")
    op.drop_index("ix_offer_snapshots_listing_scraped", table_name="offer_snapshots")
    op.drop_table("offer_snapshots")
    op.drop_index("ix_store_listings_gtin", table_name="store_listings")
    op.drop_index("ix_store_listings_canonical_product", table_name="store_listings")
    op.drop_table("store_listings")
    op.drop_index("ix_product_identifiers_canonical", table_name="product_identifiers")
    op.drop_table("product_identifiers")
    op.drop_table("canonical_products")
