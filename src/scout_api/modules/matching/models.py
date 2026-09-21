"""SQLAlchemy ORM models for product matching and offer history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from scout_api.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CanonicalProduct(Base):
    __tablename__ = "canonical_products"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Authenticated creator (JWT sub). NULL = system/legacy shared catalog row.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    variant_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    identifiers: Mapped[list[ProductIdentifier]] = relationship(
        back_populates="canonical_product", cascade="all, delete-orphan"
    )
    listings: Mapped[list[StoreListing]] = relationship(
        back_populates="canonical_product", cascade="all, delete-orphan"
    )


class ProductIdentifier(Base):
    __tablename__ = "product_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "type", "value_normalized", name="uq_product_identifiers_type_value"
        ),
        Index("ix_product_identifiers_canonical", "canonical_product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("canonical_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    value_normalized: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    canonical_product: Mapped[CanonicalProduct] = relationship(
        back_populates="identifiers"
    )


class StoreListing(Base):
    __tablename__ = "store_listings"
    __table_args__ = (
        UniqueConstraint("store", "canonical_url", name="uq_store_listings_store_url"),
        UniqueConstraint(
            "store",
            "country",
            "product_id",
            name="uq_store_listings_store_country_product_id",
        ),
        Index(
            "uq_store_listings_store_country_sku",
            "store",
            "country",
            "sku",
            unique=True,
            postgresql_where=text("sku IS NOT NULL AND btrim(sku) <> ''"),
            sqlite_where=text("sku IS NOT NULL AND trim(sku) != ''"),
        ),
        Index("ix_store_listings_canonical_product", "canonical_product_id"),
        Index("ix_store_listings_gtin", "gtin"),
        # Scheduler hot path: due monitored active listings.
        Index(
            "ix_store_listings_monitor_due",
            "next_check_at",
            postgresql_where=text(
                "monitoring_enabled IS TRUE AND status = 'active'"
            ),
            sqlite_where=text("monitoring_enabled = 1 AND status = 'active'"),
        ),
        Index(
            "ix_store_listings_promo_expires",
            "promotion_expires_at",
            postgresql_where=text("promotion_status = 'active'"),
            sqlite_where=text("promotion_status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("canonical_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    store: Mapped[str] = mapped_column(String(64), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gtin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    match_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # --- Persistent monitoring schedule (ADR 0030). Clock lives in PostgreSQL. ---
    monitoring_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_successful_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_regular_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_price_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_availability_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    last_check_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_check_scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_check_delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    check_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    check_claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    check_worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Current promotion state (history preserved via offer_events + snapshots).
    promotion_status: Mapped[str] = mapped_column(
        String(32), default="none", nullable=False
    )
    promotion_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promotion_starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    promotion_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    promotion_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    promotion_original_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    promotion_conditions: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    promotion_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    promotion_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promotion_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    canonical_product: Mapped[CanonicalProduct] = relationship(
        back_populates="listings"
    )
    snapshots: Mapped[list[OfferSnapshot]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )
    events: Mapped[list[OfferEvent]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )


class MonitorSchedulerState(Base):
    """Singleton-ish heartbeat row for monitor worker observability."""

    __tablename__ = "monitor_scheduler_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sweep_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_claimed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_processed_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class OfferSnapshot(Base):
    __tablename__ = "offer_snapshots"
    __table_args__ = (
        Index("ix_offer_snapshots_listing_scraped", "listing_id", "scraped_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("store_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    seller: Mapped[str | None] = mapped_column(String(256), nullable=True)
    availability: Mapped[str | None] = mapped_column(String(32), nullable=True)
    available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    listing: Mapped[StoreListing] = relationship(back_populates="snapshots")


class OfferEvent(Base):
    __tablename__ = "offer_events"
    __table_args__ = (
        Index("ix_offer_events_listing_detected", "listing_id", "detected_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("store_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    listing: Mapped[StoreListing] = relationship(back_populates="events")
