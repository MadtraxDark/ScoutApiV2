"""Add durable AVIF optimization lease fields on product_images (ADR 0031)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_image_optimization_lease"
down_revision: str | None = "0025_offer_monitoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_images",
        sa.Column(
            "optimization_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "product_images",
        sa.Column(
            "optimization_next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "product_images",
        sa.Column(
            "optimization_claimed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "product_images",
        sa.Column(
            "optimization_claim_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "product_images",
        sa.Column(
            "optimization_worker_id",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_product_images_optimization_due",
        "product_images",
        ["optimized_status", "optimization_next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_images_optimization_due",
        table_name="product_images",
    )
    op.drop_column("product_images", "optimization_worker_id")
    op.drop_column("product_images", "optimization_claim_expires_at")
    op.drop_column("product_images", "optimization_claimed_at")
    op.drop_column("product_images", "optimization_next_attempt_at")
    op.drop_column("product_images", "optimization_attempts")
