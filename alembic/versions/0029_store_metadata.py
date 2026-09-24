"""Persist panel-managed presentation metadata for registered stores."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_store_metadata"
down_revision: str | None = "0028_product_match_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "store_metadata",
        sa.Column("store_key", sa.String(length=64), primary_key=True),
        sa.Column("display_name", sa.String(length=160), nullable=True),
        sa.Column("logo_svg", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("store_metadata")
