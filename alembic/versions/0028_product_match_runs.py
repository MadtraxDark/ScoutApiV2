"""Persistent Product Match runs + notifications (ADR 0036)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_product_match_runs"
down_revision: str | None = "0027_exchange_rates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_match_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("reference_url", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_duration_ms", sa.Integer(), nullable=True),
        sa.Column("stores_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stores_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("no_matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["canonical_products.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_product_match_runs_product_started",
        "product_match_runs",
        ["product_id", "started_at"],
    )
    op.create_index("ix_product_match_runs_status", "product_match_runs", ["status"])
    op.create_index(
        "ix_product_match_runs_requested_by",
        "product_match_runs",
        ["requested_by"],
    )
    op.create_index(
        "uq_product_match_runs_active_product",
        "product_match_runs",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
        sqlite_where=sa.text("status IN ('pending', 'running')"),
    )
    op.create_index(
        "ix_product_match_runs_claim_due",
        "product_match_runs",
        ["status", "claim_expires_at"],
        postgresql_where=sa.text("status IN ('pending', 'running')"),
        sqlite_where=sa.text("status IN ('pending', 'running')"),
    )

    op.create_table(
        "match_store_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("store", sa.String(length=64), nullable=False),
        sa.Column("store_display_name", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("queries", sa.JSON(), nullable=False),
        sa.Column("queries_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidates_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "candidates_evaluated", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("matched_listing_id", sa.Uuid(), nullable=True),
        sa.Column("matched_url", sa.Text(), nullable=True),
        sa.Column("matched_title", sa.String(length=512), nullable=True),
        sa.Column("matched_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("matched_currency", sa.String(length=8), nullable=True),
        sa.Column("matched_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("matched_reasons", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("browser_used", sa.Boolean(), nullable=True),
        sa.Column("proxy_used", sa.Boolean(), nullable=True),
        sa.Column("search_duration_ms", sa.Integer(), nullable=True),
        sa.Column("candidate_fetch_duration_ms", sa.Integer(), nullable=True),
        sa.Column("matcher_duration_ms", sa.Integer(), nullable=True),
        sa.Column("browser_duration_ms", sa.Integer(), nullable=True),
        sa.Column("retry_duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["product_match_runs.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "store", name="uq_match_store_runs_run_store"),
    )
    op.create_index("ix_match_store_runs_run_id", "match_store_runs", ["run_id"])

    op.create_table(
        "match_candidate_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("store_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("store_product_id", sa.String(length=128), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["store_run_id"],
            ["match_store_runs.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_match_candidate_logs_store_run",
        "match_candidate_logs",
        ["store_run_id"],
    )

    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("match_run_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["canonical_products.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["match_run_id"],
            ["product_match_runs.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "match_run_id",
            "type",
            name="uq_user_notifications_match_run_type",
        ),
    )
    op.create_index("ix_user_notifications_user_id", "user_notifications", ["user_id"])
    op.create_index(
        "ix_user_notifications_user_created",
        "user_notifications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_user_notifications_user_unread",
        "user_notifications",
        ["user_id", "created_at"],
        postgresql_where=sa.text("read_at IS NULL"),
        sqlite_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_notifications_user_unread",
        table_name="user_notifications",
    )
    op.drop_index(
        "ix_user_notifications_user_created",
        table_name="user_notifications",
    )
    op.drop_index("ix_user_notifications_user_id", table_name="user_notifications")
    op.drop_table("user_notifications")
    op.drop_index(
        "ix_match_candidate_logs_store_run",
        table_name="match_candidate_logs",
    )
    op.drop_table("match_candidate_logs")
    op.drop_index("ix_match_store_runs_run_id", table_name="match_store_runs")
    op.drop_table("match_store_runs")
    op.drop_index("ix_product_match_runs_claim_due", table_name="product_match_runs")
    op.drop_index(
        "uq_product_match_runs_active_product",
        table_name="product_match_runs",
    )
    op.drop_index(
        "ix_product_match_runs_requested_by",
        table_name="product_match_runs",
    )
    op.drop_index("ix_product_match_runs_status", table_name="product_match_runs")
    op.drop_index(
        "ix_product_match_runs_product_started",
        table_name="product_match_runs",
    )
    op.drop_table("product_match_runs")
