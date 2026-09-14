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
    Numeric,
    String,
    Text,
    UniqueConstraint,
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
        Index("ix_store_listings_canonical_product", "canonical_product_id"),
        Index("ix_store_listings_gtin", "gtin"),
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

    canonical_product: Mapped[CanonicalProduct] = relationship(
        back_populates="listings"
    )
    snapshots: Mapped[list[OfferSnapshot]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )
    events: Mapped[list[OfferEvent]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
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
