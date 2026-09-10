from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProductPriceItem(BaseModel):
    """Normalized offer; monetary values are always Decimal."""

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
    installment_price: Decimal | None = None
    installment_count: int | None = None
    shipping_price: Decimal | None = None
    available: bool = True
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_changed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
