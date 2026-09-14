"""Persistence layer for canonical products, listings, and offer history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from scout_api.modules.crawler.models.product import ProductOffer, ProductPriceItem
from scout_api.modules.matching.identity import ProductIdentity
from scout_api.modules.matching.models import (
    CanonicalProduct,
    OfferEvent,
    OfferSnapshot,
    ProductIdentifier,
    StoreListing,
)
from scout_api.modules.matching.offer_diff import (
    fingerprint_from_offer,
    snapshot_dict_from_offer,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MatchingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_canonical_by_gtin(self, gtin: str) -> CanonicalProduct | None:
        stmt = (
            select(CanonicalProduct)
            .join(ProductIdentifier)
            .where(
                ProductIdentifier.type == "gtin",
                ProductIdentifier.value_normalized == gtin,
            )
            .options(selectinload(CanonicalProduct.listings))
        )
        return self._session.scalars(stmt).first()

    def get_canonical(self, canonical_id: uuid.UUID) -> CanonicalProduct | None:
        stmt = (
            select(CanonicalProduct)
            .where(CanonicalProduct.id == canonical_id)
            .options(
                selectinload(CanonicalProduct.listings).selectinload(
                    StoreListing.snapshots
                )
            )
        )
        return self._session.scalars(stmt).first()

    def get_listing(self, listing_id: uuid.UUID) -> StoreListing | None:
        stmt = (
            select(StoreListing)
            .where(StoreListing.id == listing_id)
            .options(selectinload(StoreListing.snapshots))
        )
        return self._session.scalars(stmt).first()

    def find_listing_by_url(
        self, store: str, canonical_url: str
    ) -> StoreListing | None:
        stmt = select(StoreListing).where(
            StoreListing.store == store,
            StoreListing.canonical_url == canonical_url,
        )
        return self._session.scalars(stmt).first()

    def list_listings_for_canonical(
        self, canonical_id: uuid.UUID
    ) -> list[StoreListing]:
        stmt = select(StoreListing).where(
            StoreListing.canonical_product_id == canonical_id
        )
        return list(self._session.scalars(stmt).all())

    def list_listings_by_ids(self, listing_ids: list[uuid.UUID]) -> list[StoreListing]:
        if not listing_ids:
            return []
        stmt = select(StoreListing).where(StoreListing.id.in_(listing_ids))
        return list(self._session.scalars(stmt).all())

    def upsert_canonical_from_identity(
        self,
        identity: ProductIdentity,
        *,
        title: str,
        attributes: dict[str, Any] | None = None,
    ) -> CanonicalProduct:
        product: CanonicalProduct | None = None
        if identity.gtin:
            product = self.find_canonical_by_gtin(identity.gtin)
        if product is None:
            product = CanonicalProduct(
                title=title[:512],
                brand=identity.brand,
                model=identity.model,
                variant_key=identity.variant_key,
                attributes=attributes or dict(identity.variant_attrs),
            )
            self._session.add(product)
            self._session.flush()
            if identity.gtin:
                self._session.add(
                    ProductIdentifier(
                        canonical_product_id=product.id,
                        type="gtin",
                        value_normalized=identity.gtin,
                    )
                )
        else:
            product.title = title[:512]
            product.brand = identity.brand or product.brand
            product.model = identity.model or product.model
            product.variant_key = identity.variant_key or product.variant_key
            if attributes:
                merged = dict(product.attributes or {})
                merged.update(attributes)
                product.attributes = merged
            product.updated_at = _utcnow()
        self._session.flush()
        return product

    def has_gtin(self, canonical_id: uuid.UUID, gtin: str) -> bool:
        stmt = select(ProductIdentifier).where(
            ProductIdentifier.canonical_product_id == canonical_id,
            ProductIdentifier.type == "gtin",
            ProductIdentifier.value_normalized == gtin,
        )
        return self._session.scalars(stmt).first() is not None

    def ensure_gtin_identifier(
        self,
        canonical: CanonicalProduct,
        gtin: str,
        *,
        source: str,
    ) -> bool:
        """Attach a validated GTIN to the canonical product if missing.

        Returns True when a new identifier row was created.
        """
        if self.has_gtin(canonical.id, gtin):
            return False
        # Refuse to attach a second different GTIN silently.
        existing = self._session.scalars(
            select(ProductIdentifier).where(
                ProductIdentifier.canonical_product_id == canonical.id,
                ProductIdentifier.type == "gtin",
            )
        ).first()
        if existing is not None and existing.value_normalized != gtin:
            return False
        self._session.add(
            ProductIdentifier(
                canonical_product_id=canonical.id,
                type="gtin",
                value_normalized=gtin,
            )
        )
        attrs = dict(canonical.attributes or {})
        attrs["gtin_source"] = source
        canonical.attributes = attrs
        canonical.updated_at = _utcnow()
        self._session.flush()
        return True

    def upsert_listing(
        self,
        *,
        canonical: CanonicalProduct,
        item: ProductPriceItem,
        decision: str,
        confidence: Decimal,
        status: str = "active",
    ) -> StoreListing:
        listing = self.find_listing_by_url(item.store, item.canonical_url)
        if listing is None:
            listing = StoreListing(
                canonical_product_id=canonical.id,
                store=item.store,
                country=item.country,
                product_id=item.product_id,
                sku=item.sku,
                gtin=item.gtin,
                url=item.url,
                canonical_url=item.canonical_url,
                match_decision=decision,
                confidence=confidence,
                status=status,
                title=item.title[:512] if item.title else None,
            )
            self._session.add(listing)
        else:
            listing.canonical_product_id = canonical.id
            listing.product_id = item.product_id
            listing.sku = item.sku
            listing.gtin = item.gtin
            listing.url = item.url
            listing.match_decision = decision
            listing.confidence = confidence
            listing.status = status
            listing.title = item.title[:512] if item.title else listing.title
            listing.updated_at = _utcnow()
        self._session.flush()
        return listing

    def latest_snapshot(self, listing_id: uuid.UUID) -> OfferSnapshot | None:
        stmt = (
            select(OfferSnapshot)
            .where(OfferSnapshot.listing_id == listing_id)
            .order_by(OfferSnapshot.scraped_at.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def append_snapshot_from_offer(
        self, listing: StoreListing, offer: ProductOffer
    ) -> OfferSnapshot:
        snapshot = OfferSnapshot(
            listing_id=listing.id,
            price=offer.price,
            currency=offer.currency,
            seller=offer.seller,
            availability=offer.availability,
            available=offer.available,
            fingerprint=fingerprint_from_offer(offer),
            payload=snapshot_dict_from_offer(offer),
            scraped_at=offer.scraped_at,
        )
        self._session.add(snapshot)
        self._session.flush()
        return snapshot

    def append_event(
        self,
        listing: StoreListing,
        event_type: str,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> OfferEvent:
        event = OfferEvent(
            listing_id=listing.id,
            event_type=event_type,
            before=before,
            after=after,
            detected_at=_utcnow(),
        )
        self._session.add(event)
        self._session.flush()
        return event

    def mark_listing_removed(self, listing: StoreListing) -> None:
        listing.status = "removed"
        listing.updated_at = _utcnow()
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def flush(self) -> None:
        self._session.flush()
