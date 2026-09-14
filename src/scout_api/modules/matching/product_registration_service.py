"""Explicit product registration (canonical identity + optional store listing)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from scout_api.modules.auth.schemas import AuthenticatedPrincipal, UserRole
from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.matching.identity import normalize_gtin, variant_key
from scout_api.modules.matching.models import CanonicalProduct, StoreListing
from scout_api.modules.matching.repository import MatchingRepository
from scout_api.modules.matching.schemas import (
    ProductListingView,
    ProductRegisterRequest,
    ProductRegisterResponse,
    ProductView,
)


def can_access_product(
    product: CanonicalProduct, principal: AuthenticatedPrincipal
) -> bool:
    """BOLA: private products are visible only to owner or admin."""
    if product.owner_user_id is None:
        return True
    if principal.role == UserRole.ADMIN:
        return True
    return product.owner_user_id == principal.id


class ProductRegistrationService:
    """Register catalog products without silent overwrite of existing rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def register(
        self,
        request: ProductRegisterRequest,
        *,
        owner: AuthenticatedPrincipal,
    ) -> ProductRegisterResponse:
        gtin = normalize_gtin(request.gtin)
        if request.gtin and gtin is None:
            raise RequestError(
                "GTIN/EAN/UPC inválido",
                code="INVALID_REQUEST",
            )

        store = request.store
        country = (request.country or "BR").upper() if request.store else None
        has_store_identity = bool(store and request.product_id and country)
        has_url_listing = bool(store and request.canonical_url and request.product_id)
        if gtin is None and not has_store_identity:
            raise RequestError(
                "Informe GTIN válido ou store + country + product_id "
                "(canonical_url recomendada para listing)",
                code="INVALID_REQUEST",
            )

        repo = MatchingRepository(self._session)

        if has_store_identity:
            assert store is not None and country is not None and request.product_id
            existing_listing = repo.find_listing_by_store_identity(
                store=store,
                country=country,
                product_id=request.product_id,
                sku=request.sku,
                canonical_url=(
                    str(request.canonical_url) if request.canonical_url else None
                ),
            )
            if existing_listing is not None:
                product = repo.get_canonical(existing_listing.canonical_product_id)
                if product is None:
                    raise RequestError(
                        "Listing órfão sem produto canônico",
                        code="DATABASE_ERROR",
                    )
                if not can_access_product(product, owner):
                    raise RequestError(
                        "Produto existente pertencente a outro usuário",
                        code="FORBIDDEN",
                    )
                product_view = self.get_product(product.id, viewer=owner)
                if product_view is None:
                    raise RequestError(
                        "Produto existente pertencente a outro usuário",
                        code="FORBIDDEN",
                    )
                return ProductRegisterResponse(
                    created=False,
                    listing_created=False,
                    product=product_view,
                    listing=_to_listing_view(existing_listing),
                )

        attrs = dict(request.attributes or {})
        if request.variant:
            attrs.setdefault("variant", request.variant)
        string_attrs = {k: str(v) for k, v in attrs.items() if isinstance(v, str)}
        vkey = request.variant_key or variant_key(string_attrs)

        if gtin is not None:
            existing = repo.find_canonical_by_gtin(gtin)
            if existing is not None:
                if not can_access_product(existing, owner):
                    raise RequestError(
                        "Produto existente pertencente a outro usuário",
                        code="FORBIDDEN",
                    )
                listing_view = None
                listing_created = False
                if has_url_listing or has_store_identity:
                    listing, listing_created = self._attach_listing(
                        repo, existing, request, gtin=gtin, country=country or "BR"
                    )
                    listing_view = _to_listing_view(listing)
                product_view = self.get_product(existing.id, viewer=owner)
                assert product_view is not None
                return ProductRegisterResponse(
                    created=False,
                    listing_created=listing_created,
                    product=product_view,
                    listing=listing_view,
                )

        canonical, created = repo.get_or_create_canonical(
            title=request.title,
            brand=request.brand,
            model=request.model,
            variant_key=vkey,
            attributes=attrs,
            gtin=gtin,
            owner_user_id=owner.id,
        )
        if not can_access_product(canonical, owner):
            raise RequestError(
                "Produto existente pertencente a outro usuário",
                code="FORBIDDEN",
            )
        listing_view = None
        listing_created = False
        if has_url_listing or (has_store_identity and request.canonical_url):
            listing, listing_created = self._attach_listing(
                repo, canonical, request, gtin=gtin, country=country or "BR"
            )
            listing_view = _to_listing_view(listing)
        elif has_store_identity and not request.canonical_url:
            # Store identity without URL: still persist listing with synthetic URL.
            assert store and request.product_id
            synthetic = f"scout://{store}/{country}/{request.product_id}"
            listing, listing_created = repo.get_or_create_listing(
                canonical=canonical,
                store=store,
                country=country or "BR",
                product_id=request.product_id,
                url=synthetic,
                canonical_url=synthetic,
                sku=request.sku,
                gtin=gtin,
                title=request.title,
            )
            listing_view = _to_listing_view(listing)
        self._session.flush()
        product_view = self.get_product(canonical.id, viewer=owner)
        assert product_view is not None
        return ProductRegisterResponse(
            created=created,
            listing_created=listing_created,
            product=product_view,
            listing=listing_view,
        )

    def get_product(
        self,
        product_id: UUID,
        *,
        viewer: AuthenticatedPrincipal | None = None,
    ) -> ProductView | None:
        repo = MatchingRepository(self._session)
        canonical = repo.get_canonical(product_id)
        if canonical is None:
            return None
        if viewer is not None and not can_access_product(canonical, viewer):
            return None
        listings = list(canonical.listings or [])
        if not listings:
            listings = repo.list_listings_for_canonical(canonical.id)
        return _to_product_view(canonical, listings)

    @staticmethod
    def _attach_listing(
        repo: MatchingRepository,
        canonical: CanonicalProduct,
        request: ProductRegisterRequest,
        *,
        gtin: str | None,
        country: str,
    ) -> tuple[StoreListing, bool]:
        assert request.store and request.product_id
        canonical_url = str(
            request.canonical_url
            or f"scout://{request.store}/{country}/{request.product_id}"
        )
        url = str(request.url or request.canonical_url or canonical_url)
        return repo.get_or_create_listing(
            canonical=canonical,
            store=request.store,
            country=country,
            product_id=request.product_id,
            url=url,
            canonical_url=canonical_url,
            sku=request.sku,
            gtin=gtin,
            title=request.title,
            match_decision="auto_match",
            confidence=Decimal("1.0000"),
            status="active",
        )


def _to_product_view(
    product: CanonicalProduct, listings: list[StoreListing]
) -> ProductView:
    gtins = [
        ident.value_normalized
        for ident in (product.identifiers or [])
        if ident.type == "gtin"
    ]
    if not gtins:
        gtins = [item.gtin for item in listings if item.gtin]
    seen: set[str] = set()
    unique_gtins: list[str] = []
    for value in gtins:
        if value not in seen:
            seen.add(value)
            unique_gtins.append(value)
    return ProductView(
        id=product.id,
        title=product.title,
        brand=product.brand,
        model=product.model,
        variant_key=product.variant_key,
        attributes=dict(product.attributes or {}),
        gtins=unique_gtins,
        created_at=product.created_at,
        updated_at=product.updated_at,
        listings=[_to_listing_view(item) for item in listings],
    )


def _to_listing_view(listing: StoreListing) -> ProductListingView:
    return ProductListingView(
        id=listing.id,
        store=listing.store,
        country=listing.country,
        product_id=listing.product_id,
        sku=listing.sku,
        gtin=listing.gtin,
        url=listing.url,
        canonical_url=listing.canonical_url,
        status=listing.status,
        title=listing.title,
        match_decision=listing.match_decision,
        confidence=listing.confidence,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
    )
