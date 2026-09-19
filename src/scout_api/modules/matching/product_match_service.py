"""Orchestrate cross-store product matching with optional persistence."""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.core.fingerprints import canonicalize_url
from scout_api.modules.crawler.models.product import (
    ProductPriceItem,
    product_offer_from_price_item,
)
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.crawler.services.store_resolver import stores_supporting_search
from scout_api.modules.matching.engine import MatchingEngine
from scout_api.modules.matching.gtin_learning import (
    TrustedGtin,
    identity_with_gtin,
    resolve_trusted_gtin,
)
from scout_api.modules.matching.identity import (
    build_search_queries,
    identity_from_price_item,
    normalize_gtin,
)
from scout_api.modules.matching.repository import MatchingRepository
from scout_api.modules.matching.schemas import (
    MatchHit,
    MatchRequest,
    MatchResponse,
    MatchStoreError,
)
from scout_api.modules.matching.store_search_order import order_stores_for_match
from scout_api.modules.matching.store_search_service import StoreSearchService

logger = logging.getLogger(__name__)

# Fallback when the spider registry has no search-capable stores; order mirrors
# GTIN exposure priority (kabum / bestbuy / … before magalu / shopee).
MVP_SEARCH_STORES = (
    "kabum",
    "bestbuy",
    "nissei",
    "shoppingchina",
    "amazon_br",
    "amazon_us",
    "magazineluiza",
    "shopee",
)

_MAX_RATE_LIMIT_WAIT_SECONDS = 20.0
# Cap empty SERP retries so blocked/expensive stores (Shopee) cannot burn
# N queries × multi-minute browser sessions when the first searches return [].
# Identifier-only misses (bare MPN/GTIN) do not count — the next commercial
# series query may still recover the SKU (e.g. CFI-2114B vs CFI-2115B on SC).
_MAX_EMPTY_SEARCH_QUERIES = 2


def _is_identifier_only_query(query: str) -> bool:
    """True for bare GTIN/MPN queries that often miss across store revisions."""
    text = (query or "").strip()
    if not text:
        return False
    if " " not in text:
        return len(text) >= 6
    parts = text.split()
    if len(parts) == 2 and parts[0].casefold() in {
        "sony",
        "apple",
        "samsung",
        "kingston",
        "corsair",
    }:
        return len(parts[1]) >= 6
    return False


class ProductMatchService:
    def __init__(
        self,
        *,
        scrape_service: ProductScrapeService | None = None,
        search_service: StoreSearchService | None = None,
        engine: MatchingEngine | None = None,
        session: Session | None = None,
    ) -> None:
        self._scrape = scrape_service or ProductScrapeService()
        self._search = search_service or StoreSearchService()
        self._engine = engine or MatchingEngine()
        self._session = session

    def match(self, request: MatchRequest) -> MatchResponse:
        reference = self._scrape.scrape(
            str(request.reference_url),
            include_images=request.include_images,
        )
        ref_identity = identity_from_price_item(reference)
        queries = build_search_queries(ref_identity)
        target_stores = self._resolve_stores(
            request.stores,
            reference,
            reference_has_gtin=bool(ref_identity.gtin),
        )

        matches: list[MatchHit] = []
        unmatched: list[str] = []
        errors: list[MatchStoreError] = []
        best_by_store: dict[str, MatchHit] = {}
        learned: TrustedGtin | None = None
        if ref_identity.gtin:
            learned = TrustedGtin(gtin=ref_identity.gtin, source="reference")

        for store_key in target_stores:
            if not self._search.is_search_supported(store_key):
                errors.append(
                    MatchStoreError(
                        store=store_key,
                        code="SEARCH_UNSUPPORTED",
                        message=f"Busca ao vivo não disponível para {store_key}",
                    )
                )
                unmatched.append(store_key)
                continue

            store_matched = False
            last_error: MatchStoreError | None = None
            empty_searches = 0
            for query in queries:
                try:
                    candidates = self._search.search(
                        store_key,
                        query,
                        limit=request.max_candidates_per_store,
                    )
                except RequestError as exc:
                    last_error = MatchStoreError(
                        store=store_key,
                        code=exc.code,
                        message=str(exc),
                    )
                    if exc.code == "SEARCH_UNSUPPORTED":
                        break
                    continue
                except ParseError as exc:
                    last_error = MatchStoreError(
                        store=store_key,
                        code="PARSE_ERROR",
                        message=str(exc),
                    )
                    continue

                if not candidates:
                    if not _is_identifier_only_query(query):
                        empty_searches += 1
                    if empty_searches >= _MAX_EMPTY_SEARCH_QUERIES:
                        logger.info(
                            "match_empty_search_cap",
                            extra={
                                "store": store_key,
                                "empty_searches": empty_searches,
                            },
                        )
                        break
                    continue

                empty_searches = 0
                for candidate in candidates:
                    if canonicalize_url(candidate.url) == canonicalize_url(
                        reference.canonical_url
                    ):
                        continue
                    product = self._scrape_candidate(
                        candidate.url,
                        store_key=store_key,
                        include_images=request.include_images,
                    )
                    if product is None:
                        continue

                    score = self._engine.score(
                        ref_identity, identity_from_price_item(product)
                    )
                    if score.decision == "reject":
                        continue
                    if score.decision == "review" and not request.include_review:
                        continue

                    hit = MatchHit(
                        store=product.store,
                        country=product.country,
                        decision=score.decision,
                        confidence=score.confidence,
                        reasons=list(score.reasons),
                        product=product,
                        search_query=query,
                    )
                    existing = best_by_store.get(store_key)
                    if existing is None or hit.confidence > existing.confidence:
                        best_by_store[store_key] = hit
                    if score.decision == "auto_match":
                        store_matched = True
                        learned = self._maybe_learn_gtin(learned, ref_identity, hit)
                        if learned and not ref_identity.gtin:
                            ref_identity = identity_with_gtin(
                                ref_identity, learned.gtin
                            )
                            queries = build_search_queries(ref_identity)
                            logger.info(
                                "trusted_gtin_learned",
                                extra={
                                    "gtin": learned.gtin,
                                    "source": learned.source,
                                },
                            )

                if store_matched:
                    break

            if store_key in best_by_store:
                matches.append(best_by_store[store_key])
            else:
                unmatched.append(store_key)
                if last_error is not None:
                    errors.append(last_error)

        # Final consensus across all auto-matches (guards mid-flight conflicts).
        trusted = resolve_trusted_gtin(ref_identity, matches)
        if trusted is None and learned and learned.source == "reference":
            trusted = learned
        elif trusted is not None:
            learned = trusted

        if learned and learned.source != "reference" and not reference.gtin:
            reference = reference.model_copy(update={"gtin": learned.gtin})

        canonical_id = None
        if request.persist:
            if self._session is None:
                raise RequestError(
                    "Persistência requer DATABASE_URL / sessão SQLAlchemy",
                    code="DATABASE_UNAVAILABLE",
                )
            canonical_id = self._persist(reference, matches, learned)

        return MatchResponse(
            canonical_product_id=canonical_id,
            reference=reference,
            matches=matches,
            unmatched_stores=unmatched,
            errors=errors,
            discovered_gtin=learned.gtin if learned else None,
            gtin_source=learned.source if learned else None,
        )

    @staticmethod
    def _maybe_learn_gtin(
        current: TrustedGtin | None,
        reference_identity: object,
        hit: MatchHit,
    ) -> TrustedGtin | None:
        """Adopt a candidate GTIN mid-flight only under safe auto_match rules."""
        from scout_api.modules.matching.identity import ProductIdentity

        assert isinstance(reference_identity, ProductIdentity)
        cand = normalize_gtin(hit.product.gtin)
        if not cand or hit.decision != "auto_match":
            return current
        probe = resolve_trusted_gtin(reference_identity, [hit])
        if probe is None:
            return current
        if current is None:
            return TrustedGtin(gtin=cand, source=f"auto_match:{hit.store}")
        if current.gtin == cand:
            return current
        # Conflict with a previously learned barcode → drop learning.
        logger.warning(
            "trusted_gtin_conflict",
            extra={"previous": current.gtin, "candidate": cand},
        )
        return current if current.source == "reference" else None

    def _scrape_candidate(
        self,
        url: str,
        *,
        store_key: str,
        include_images: bool,
    ) -> ProductPriceItem | None:
        """Scrape a SERP candidate; wait once on domain RATE_LIMITED."""
        try:
            return self._scrape.scrape(url, include_images=include_images)
        except ParseError as exc:
            logger.info(
                "match_candidate_scrape_failed",
                extra={"store": store_key, "url": url, "error": str(exc)},
            )
            return None
        except RequestError as exc:
            if exc.code != "RATE_LIMITED":
                logger.info(
                    "match_candidate_scrape_failed",
                    extra={
                        "store": store_key,
                        "url": url,
                        "error": str(exc),
                        "code": exc.code,
                    },
                )
                return None
            wait = float(exc.retry_after or 15)
            wait = min(max(wait, 0.5), _MAX_RATE_LIMIT_WAIT_SECONDS)
            logger.info(
                "match_candidate_rate_limited_retry",
                extra={"store": store_key, "url": url, "wait_s": wait},
            )
            time.sleep(wait)
            try:
                return self._scrape.scrape(url, include_images=include_images)
            except (RequestError, ParseError) as retry_exc:
                logger.info(
                    "match_candidate_scrape_failed",
                    extra={
                        "store": store_key,
                        "url": url,
                        "error": str(retry_exc),
                    },
                )
                return None

    def _persist(
        self,
        reference: ProductPriceItem,
        matches: list[MatchHit],
        learned: TrustedGtin | None,
    ) -> UUID:
        assert self._session is not None
        repo = MatchingRepository(self._session)
        ref_identity = identity_from_price_item(reference)
        if learned and not ref_identity.gtin:
            ref_identity = identity_with_gtin(ref_identity, learned.gtin)
        canonical = repo.upsert_canonical_from_identity(
            ref_identity,
            title=reference.title,
            attributes=dict(ref_identity.variant_attrs),
        )
        if learned:
            created = repo.ensure_gtin_identifier(
                canonical, learned.gtin, source=learned.source
            )
            if created:
                logger.info(
                    "canonical_gtin_persisted",
                    extra={"gtin": learned.gtin, "source": learned.source},
                )

        ref_listing = repo.upsert_listing(
            canonical=canonical,
            item=reference,
            decision="auto_match",
            confidence=Decimal("1.0000"),
            status="active",
        )
        ref_offer = product_offer_from_price_item(reference)
        if repo.latest_snapshot(ref_listing.id) is None:
            repo.append_snapshot_from_offer(ref_listing, ref_offer)
            repo.append_event(
                ref_listing, "offer_created", after={"url": reference.url}
            )
        if learned and learned.source != "reference":
            repo.append_event(
                ref_listing,
                "gtin_learned",
                after={"gtin": learned.gtin, "source": learned.source},
            )

        for hit in matches:
            if hit.decision == "reject":
                continue
            status = "review" if hit.decision == "review" else "active"
            listing = repo.upsert_listing(
                canonical=canonical,
                item=hit.product,
                decision=hit.decision,
                confidence=hit.confidence,
                status=status,
            )
            hit.listing_id = listing.id
            offer = product_offer_from_price_item(hit.product)
            repo.append_snapshot_from_offer(listing, offer)
            repo.append_event(
                listing,
                "offer_created",
                after={"url": hit.product.url, "decision": hit.decision},
            )
        self._session.flush()
        return canonical.id

    @staticmethod
    def _resolve_stores(
        requested: list[str] | None,
        reference: ProductPriceItem,
        *,
        reference_has_gtin: bool = False,
    ) -> list[str]:
        available = list(stores_supporting_search()) or list(MVP_SEARCH_STORES)
        if requested:
            selected = [s.strip().lower() for s in requested if s.strip()]
        else:
            selected = list(available)
        return order_stores_for_match(
            selected,
            reference_store=reference.store,
            reference_has_gtin=reference_has_gtin,
        )
