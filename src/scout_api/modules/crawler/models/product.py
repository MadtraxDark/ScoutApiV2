from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Availability = Literal["available", "out_of_stock", "unavailable"]


class ProductOffer(BaseModel):
    """Commercial snapshot used for lightweight price/availability checks."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    store: str
    country: str
    product_id: str
    sku: str | None = None
    seller: str | None = None
    url: str
    canonical_url: str
    currency: str
    price: Decimal = Field(gt=0)
    original_price: Decimal | None = None
    discount_percentage: Decimal | None = None
    pix_price: Decimal | None = None
    installment_price: Decimal | None = None
    installment_count: int | None = None
    availability: Availability = "available"
    available: bool = True
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductDetails(BaseModel):
    """Catalog identity and descriptive fields for the full product scrape."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    product_id: str
    sku: str | None = None
    gtin: str | None = None
    title: str
    brand: str | None = None
    model: str | None = None
    variant: str | None = None
    description: str | None = None
    specifications: dict[str, Any] = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductPriceItem(BaseModel):
    """Normalized full product scrape; monetary values are always Decimal."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    store: str
    country: str
    product_id: str
    sku: str | None = None
    gtin: str | None = None
    title: str
    brand: str | None = None
    model: str | None = None
    variant: str | None = None
    seller: str | None = None
    url: str
    canonical_url: str
    currency: str
    price: Decimal = Field(gt=0)
    original_price: Decimal | None = None
    discount_percentage: Decimal | None = None
    pix_price: Decimal | None = None
    availability: Availability = "available"
    installment_price: Decimal | None = None
    installment_count: int | None = None
    shipping_price: Decimal | None = None
    available: bool = True
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_changed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def compose_product_price_item(
    offer: ProductOffer,
    details: ProductDetails,
    *,
    shipping_price: Decimal | None = None,
    last_changed_at: datetime | None = None,
) -> ProductPriceItem:
    """Merge commercial offer and catalog details into the public full item."""
    offer_meta = offer.metadata if isinstance(offer.metadata, dict) else {}
    details_meta = details.metadata if isinstance(details.metadata, dict) else {}
    merged_source: dict[str, Any] = {}
    offer_source = offer_meta.get("source")
    details_source = details_meta.get("source")
    if isinstance(offer_source, dict):
        merged_source.update(offer_source)
    if isinstance(details_source, dict):
        merged_source.update(details_source)

    metadata = {
        **details_meta,
        **offer_meta,
        "source": merged_source
        or offer_meta.get("source")
        or details_meta.get("source"),
    }
    return ProductPriceItem(
        store=offer.store,
        country=offer.country,
        product_id=offer.product_id or details.product_id,
        sku=offer.sku or details.sku,
        gtin=details.gtin,
        title=details.title,
        brand=details.brand,
        model=details.model,
        variant=details.variant,
        seller=offer.seller,
        url=offer.url,
        canonical_url=offer.canonical_url,
        currency=offer.currency,
        price=offer.price,
        original_price=offer.original_price,
        discount_percentage=offer.discount_percentage,
        pix_price=offer.pix_price,
        installment_price=offer.installment_price,
        installment_count=offer.installment_count,
        shipping_price=shipping_price,
        available=offer.available,
        availability=offer.availability,
        scraped_at=offer.scraped_at,
        last_changed_at=last_changed_at,
        metadata=metadata,
    )


def product_offer_from_price_item(item: ProductPriceItem) -> ProductOffer:
    """Project a cached full item into the lightweight offer contract."""
    return ProductOffer(
        store=item.store,
        country=item.country,
        product_id=item.product_id,
        sku=item.sku,
        seller=item.seller,
        url=item.url,
        canonical_url=item.canonical_url,
        currency=item.currency,
        price=item.price,
        original_price=item.original_price,
        discount_percentage=item.discount_percentage,
        pix_price=item.pix_price,
        installment_price=item.installment_price,
        installment_count=item.installment_count,
        availability=item.availability,
        available=item.available,
        scraped_at=item.scraped_at,
        metadata=item.metadata,
    )
