"""Add store listing dedup constraints for concurrent-safe product identity."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_store_listing_dedup"
down_revision: str | None = "0019_matching_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail closed if unexpected duplicates appear before locking the keys.
    conn = op.get_bind()
    dup_pid = conn.execute(
        sa.text(
            """
            SELECT store, country, product_id, count(*) AS n
            FROM store_listings
            GROUP BY store, country, product_id
            HAVING count(*) > 1
            LIMIT 5
            """
        )
    ).fetchall()
    if dup_pid:
        raise RuntimeError(
            "Não é seguro criar uq_store_listings_store_country_product_id: "
            f"duplicatas existentes={dup_pid!r}. Resolva manualmente antes."
        )
    dup_sku = conn.execute(
        sa.text(
            """
            SELECT store, country, sku, count(*) AS n
            FROM store_listings
            WHERE sku IS NOT NULL AND btrim(sku) <> ''
            GROUP BY store, country, sku
            HAVING count(*) > 1
            LIMIT 5
            """
        )
    ).fetchall()
    if dup_sku:
        raise RuntimeError(
            "Não é seguro criar uq_store_listings_store_country_sku: "
            f"duplicatas existentes={dup_sku!r}. Resolva manualmente antes."
        )

    op.create_unique_constraint(
        "uq_store_listings_store_country_product_id",
        "store_listings",
        ["store", "country", "product_id"],
    )
    op.create_index(
        "uq_store_listings_store_country_sku",
        "store_listings",
        ["store", "country", "sku"],
        unique=True,
        postgresql_where=sa.text("sku IS NOT NULL AND btrim(sku) <> ''"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_store_listings_store_country_sku",
        table_name="store_listings",
        postgresql_where=sa.text("sku IS NOT NULL AND btrim(sku) <> ''"),
    )
    op.drop_constraint(
        "uq_store_listings_store_country_product_id",
        "store_listings",
        type_="unique",
    )
