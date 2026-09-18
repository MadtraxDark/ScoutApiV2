"""Pydantic schemas and search candidate DTOs for product matching."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from scout_api.modules.crawler.models.product import ProductOffer, ProductPriceItem
from scout_api.modules.crawler.models.search import SearchCandidate

MatchDecision = Literal["auto_match", "review", "reject"]
ListingStatus = Literal["active", "removed", "review"]
OfferEventType = Literal[
    "offer_created",
    "unchanged",
    "price_changed",
    "seller_changed",
    "availability_changed",
    "offer_removed",
    "out_of_stock",
    "new_offer",
    "scrape_failed",
]
RefreshStatus = Literal[
    "unchanged",
    "changed",
    "removed",
    "out_of_stock",
    "scrape_failed",
    "new_offer",
]

__all__ = [
    "SearchCandidate",
    "MatchDecision",
    "ListingStatus",
    "OfferEventType",
    "RefreshStatus",
    "MatchReason",
    "MatchRequest",
    "MatchHit",
    "MatchStoreError",
    "MatchResponse",
    "OfferRefreshRequest",
    "OfferSnapshotView",
    "OfferEventView",
    "OfferRefreshResult",
    "OfferRefreshResponse",
    "ProductRegisterRequest",
    "ProductListingView",
    "ProductView",
    "ProductRegisterResponse",
]


class MatchReason(BaseModel):
    code: str
    detail: str
    score: float | None = None


class MatchRequest(BaseModel):
    reference_url: HttpUrl = Field(
        description="URL do produto de referência usado como base do matching."
    )
    stores: list[str] | None = Field(
        default=None,
        description="Lista de lojas a consultar; se omitida, usa o conjunto padrão.",
    )
    include_review: bool = Field(
        default=False,
        description="Quando true, inclui candidatas classificadas como review.",
    )
    persist: bool = Field(
        default=True,
        description="Quando true, persiste produto canônico e listings no banco.",
    )
    include_images: bool = Field(
        default=False,
        description="Quando true, inclui galeria de imagens no scraping de referência.",
    )
    max_candidates_per_store: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Máximo de candidatos avaliados por loja.",
    )


class MatchHit(BaseModel):
    store: str
    country: str
    listing_id: UUID | None = None
    decision: MatchDecision
    confidence: Decimal
    reasons: list[MatchReason] = Field(default_factory=list)
    product: ProductPriceItem
    search_query: str | None = None


class MatchStoreError(BaseModel):
    store: str
    code: str
    message: str


class MatchResponse(BaseModel):
    canonical_product_id: UUID | None = None
    reference: ProductPriceItem
    matches: list[MatchHit] = Field(default_factory=list)
    unmatched_stores: list[str] = Field(default_factory=list)
    errors: list[MatchStoreError] = Field(default_factory=list)
    discovered_gtin: str | None = None
    gtin_source: str | None = None
    """``reference`` or ``auto_match:<store>`` when a trusted GTIN was learned."""


class OfferRefreshRequest(BaseModel):
    canonical_product_id: UUID | None = Field(
        default=None,
        description="Produto canônico cujas ofertas devem ser atualizadas.",
    )
    listing_ids: list[UUID] | None = Field(
        default=None,
        description="Listings específicos a atualizar.",
    )
    urls: list[HttpUrl] | None = Field(
        default=None,
        description="URLs avulsas de oferta a atualizar.",
    )
    include_details: bool = Field(
        default=False,
        description="Quando true, inclui snapshots e eventos detalhados na resposta.",
    )


class OfferSnapshotView(BaseModel):
    price: Decimal | None = None
    currency: str | None = None
    seller: str | None = None
    availability: str | None = None
    available: bool | None = None
    scraped_at: datetime | None = None
    fingerprint: str | None = None


class OfferEventView(BaseModel):
    event_type: OfferEventType
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    detected_at: datetime


class OfferRefreshResult(BaseModel):
    listing_id: UUID | None = None
    store: str | None = None
    url: str
    status: RefreshStatus
    events: list[OfferEventView] = Field(default_factory=list)
    previous: OfferSnapshotView | None = None
    current: OfferSnapshotView | None = None
    offer: ProductOffer | None = None
    error: str | None = None


class OfferRefreshResponse(BaseModel):
    results: list[OfferRefreshResult] = Field(default_factory=list)


class ProductRegisterRequest(BaseModel):
    """Cadastro de produto canônico, com listing de loja opcional.

    Deduplica por GTIN, identificadores de loja, SKU ou URL canônica.
    Produtos/listings existentes são reutilizados sem sobrescrita silenciosa.
    """

    model_config = {"extra": "forbid"}

    title: str = Field(
        min_length=1,
        max_length=512,
        description="Título do produto canônico.",
    )
    brand: str | None = Field(default=None, max_length=128, description="Marca.")
    model: str | None = Field(default=None, max_length=128, description="Modelo.")
    variant: str | None = Field(
        default=None,
        max_length=256,
        description="Variante legível (cor, capacidade, etc.).",
    )
    variant_key: str | None = Field(
        default=None,
        max_length=256,
        description="Chave normalizada da variante para deduplicação.",
    )
    gtin: str | None = Field(
        default=None, max_length=32, description="GTIN/EAN/UPC quando conhecido."
    )
    attributes: dict[str, Any] | None = Field(
        default=None, description="Atributos adicionais do produto."
    )
    store: str | None = Field(
        default=None, max_length=64, description="Loja do listing opcional."
    )
    country: str | None = Field(
        default=None, max_length=8, description="País do listing (código curto)."
    )
    product_id: str | None = Field(
        default=None,
        max_length=128,
        description="Identificador do produto na loja.",
    )
    sku: str | None = Field(
        default=None, max_length=128, description="SKU na loja, quando disponível."
    )
    url: HttpUrl | None = Field(
        default=None, description="URL da página do produto na loja."
    )
    canonical_url: HttpUrl | None = Field(
        default=None, description="URL canônica do listing na loja."
    )


class ProductListingView(BaseModel):
    id: UUID
    store: str
    country: str
    product_id: str
    sku: str | None = None
    gtin: str | None = None
    url: str
    canonical_url: str
    status: str
    title: str | None = None
    match_decision: str
    confidence: Decimal
    created_at: datetime
    updated_at: datetime


class ProductView(BaseModel):
    id: UUID
    title: str
    brand: str | None = None
    model: str | None = None
    variant_key: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    gtins: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    listings: list[ProductListingView] = Field(default_factory=list)


class ProductRegisterResponse(BaseModel):
    created: bool
    listing_created: bool = False
    product: ProductView
    listing: ProductListingView | None = None
