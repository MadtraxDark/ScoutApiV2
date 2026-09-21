"""Orchestrate cross-store product matching with optional persistence."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from scout_api.core.performance import (
    DuplicateWorkTracker,
    OperationCategory,
    format_stage_summary,
    observe,
)
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
from scout_api.modules.crawler.stores import STORE_CONFIGS
from scout_api.modules.matching.engine import MatchingEngine
from scout_api.modules.matching.gtin_learning import (
    TrustedGtin,
    identity_with_gtin,
    resolve_trusted_gtin,
)
from scout_api.modules.matching.identity import (
    ProductIdentity,
    build_search_queries,
    critical_identity_conflict,
    form_factor_conflict,
    identity_from_price_item,
    identity_reference_item,
    looks_like_accessory,
    looks_like_bundle,
    normalize_brand,
    normalize_gtin,
)
from scout_api.modules.matching.repository import MatchingRepository
from scout_api.modules.matching.schemas import (
    MatchHit,
    MatchProgressEvent,
    MatchRequest,
    MatchResponse,
    MatchStoreError,
)
from scout_api.modules.matching.store_search_order import order_stores_for_match
from scout_api.modules.matching.store_search_service import StoreSearchService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[MatchProgressEvent], None]

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
    "mercadolivre",
    "shopee",
    "aliexpress",
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
    if len(parts) == 2:
        # brand + manufacturer PN (including MSI-style board / GPU codes)
        from scout_api.modules.matching.identity import looks_like_mpn, normalize_mpn

        second = normalize_mpn(parts[1]) or parts[1]
        compact = re.sub(r"[^a-z0-9]", "", parts[1].casefold())
        if looks_like_mpn(second) or len(compact) >= 8:
            return True
        if parts[0].casefold() in {
            "sony",
            "apple",
            "samsung",
            "kingston",
            "corsair",
            "msi",
            "asus",
            "gigabyte",
        }:
            return len(parts[1]) >= 6
    return False


def _serp_title_reject_reason(
    reference: ProductIdentity,
    *,
    title: str | None,
) -> str | None:
    """Cheap reject from SERP title before spending a full PDP scrape.

    Missing title → unknown (do not reject). Only clear conflicts skip scrape.
    """
    if not (title or "").strip():
        return None
    title_text = title.strip() if title else ""
    if looks_like_accessory(title_text, reference_title=reference.title):
        return "accessory_reject"
    if looks_like_bundle(title_text, reference_title=reference.title):
        return "bundle_reject"
    form = form_factor_conflict(reference.title, title_text)
    if form:
        return form
    probe = identity_from_price_item(identity_reference_item(title_text))
    critical = critical_identity_conflict(reference, probe)
    if critical:
        return critical
    ref_brand = normalize_brand(reference.brand) if reference.brand else None
    cand_brand = probe.brand
    if ref_brand and cand_brand and ref_brand != cand_brand:
        if ref_brand not in cand_brand and cand_brand not in ref_brand:
            return f"brand_mismatch:{ref_brand}!={cand_brand}"
    return None


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

    def match(
        self,
        request: MatchRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> MatchResponse:
        """Match from a live reference URL (scrape → search → score)."""
        if on_progress is not None:
            on_progress(
                MatchProgressEvent(
                    type="search_progress",
                    stage="reference",
                    status="running",
                    message="Coletando produto de referência",
                    sequence=0,
                )
            )
        reference = self._scrape.scrape(
            str(request.reference_url),
            include_images=request.include_images,
        )
        return self.match_from_item(
            reference,
            stores=request.stores,
            include_review=request.include_review,
            persist=request.persist,
            include_images=request.include_images,
            max_candidates_per_store=request.max_candidates_per_store,
            clear_reference_price=False,
            on_progress=on_progress,
        )

    def match_from_item(
        self,
        reference: ProductPriceItem,
        *,
        stores: list[str] | None = None,
        include_review: bool = False,
        persist: bool = False,
        include_images: bool = False,
        max_candidates_per_store: int = 5,
        clear_reference_price: bool = True,
        on_progress: ProgressCallback | None = None,
    ) -> MatchResponse:
        """Match using an already-normalized reference item (no reference scrape).

        Intended for identity-only discovery: brand/model(/variant) without
        feeding known store URLs into Search. When ``clear_reference_price`` is
        true (default), the reference price is ignored so a synthetic identity
        placeholder cannot trigger extreme-price ``review``/reject gates.
        """
        ref_identity = identity_from_price_item(reference)
        if clear_reference_price:
            ref_identity = replace(ref_identity, price=None)
        return self._match_with_reference(
            reference,
            ref_identity,
            stores=stores,
            include_review=include_review,
            persist=persist,
            include_images=include_images,
            max_candidates_per_store=max_candidates_per_store,
            on_progress=on_progress,
        )

    def _match_with_reference(
        self,
        reference: ProductPriceItem,
        ref_identity: ProductIdentity,
        *,
        stores: list[str] | None,
        include_review: bool,
        persist: bool,
        include_images: bool,
        max_candidates_per_store: int,
        on_progress: ProgressCallback | None = None,
    ) -> MatchResponse:
        queries = build_search_queries(ref_identity)
        target_stores = self._resolve_stores(
            stores,
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

        seq = 0

        def emit(**kwargs: object) -> None:
            nonlocal seq
            if on_progress is None:
                return
            seq += 1
            payload = dict(kwargs)
            payload.setdefault("sequence", seq)
            on_progress(MatchProgressEvent.model_validate(payload))

        match_t0 = time.perf_counter()
        store_stage_ms: dict[str, dict[str, object]] = {}
        dup_tracker = DuplicateWorkTracker()
        for store_key in target_stores:
            display = STORE_CONFIGS.get(store_key)
            display_name = store_key if display is None else store_key
            emit(
                type="store_started",
                store=store_key,
                display_name=display_name,
                stage="store_started",
                status="running",
                message=f"Iniciando busca em {store_key}",
            )
            if not self._search.is_search_supported(store_key):
                err = MatchStoreError(
                    store=store_key,
                    code="SEARCH_UNSUPPORTED",
                    message=f"Busca ao vivo não disponível para {store_key}",
                )
                errors.append(err)
                unmatched.append(store_key)
                emit(
                    type="error",
                    store=store_key,
                    display_name=display_name,
                    stage="search_unsupported",
                    status="error",
                    message=err.message,
                )
                continue

            store_t0 = time.perf_counter()
            store_matched = False
            last_error: MatchStoreError | None = None
            empty_searches = 0
            candidates_seen = 0
            scrape_failures = 0
            title_rejects = 0
            scrapes_done = 0
            search_ms_total = 0.0
            scrape_ms_total = 0.0
            last_scrape_error: MatchStoreError | None = None
            for query in queries:
                emit(
                    type="searching",
                    store=store_key,
                    display_name=display_name,
                    stage="searching",
                    status="running",
                    message=f"Buscando: {query}",
                )
                try:
                    search_t0 = time.perf_counter()
                    candidates = self._search.search(
                        store_key,
                        query,
                        limit=max_candidates_per_store,
                    )
                    search_ms = (time.perf_counter() - search_t0) * 1000
                    search_ms_total += search_ms
                    observe(
                        "product_search",
                        search_ms,
                        category=OperationCategory.PRODUCT_SEARCH,
                        stage=store_key,
                        context={
                            "query_len": len(query),
                            "candidates": len(candidates),
                        },
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
                emit(
                    type="candidates_found",
                    store=store_key,
                    display_name=display_name,
                    stage="candidates_found",
                    status="running",
                    message=f"{len(candidates)} candidatos encontrados",
                    candidate_count=len(candidates),
                )
                logger.debug(
                    "match_store_search",
                    extra={
                        "store": store_key,
                        "query": query,
                        "candidates": len(candidates),
                        "search_ms": round(search_ms, 1),
                    },
                )
                for candidate in candidates:
                    if canonicalize_url(candidate.url) == canonicalize_url(
                        reference.canonical_url
                    ):
                        continue
                    candidates_seen += 1
                    reject = _serp_title_reject_reason(
                        ref_identity, title=candidate.title
                    )
                    if reject is not None:
                        title_rejects += 1
                        logger.debug(
                            "match_serp_title_reject",
                            extra={
                                "store": store_key,
                                "reason": reject,
                                "title": (candidate.title or "")[:120],
                            },
                        )
                        continue
                    canon = canonicalize_url(candidate.url)
                    dup_count = dup_tracker.record("scrape_url", canon)
                    emit(
                        type="scraping_candidate",
                        store=store_key,
                        display_name=display_name,
                        stage="scraping_candidate",
                        status="running",
                        message="Avaliando candidato",
                    )
                    scrape_t0 = time.perf_counter()
                    product, scrape_error = self._scrape_candidate(
                        candidate.url,
                        store_key=store_key,
                        include_images=include_images,
                    )
                    scrapes_done += 1
                    scrape_ms = (time.perf_counter() - scrape_t0) * 1000
                    scrape_ms_total += scrape_ms
                    observe(
                        "product_scrape",
                        scrape_ms,
                        category=OperationCategory.CRAWLER,
                        stage=store_key,
                        context={
                            "duplicate_scrape": dup_count > 1,
                            "ok": product is not None,
                        },
                    )
                    if product is None:
                        scrape_failures += 1
                        if scrape_error is not None:
                            last_scrape_error = scrape_error
                        continue

                    score = self._engine.score(
                        ref_identity, identity_from_price_item(product)
                    )
                    if score.decision == "reject":
                        continue
                    if score.decision == "review" and not include_review:
                        continue

                    hit = MatchHit(
                        store=store_key,
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
                        logger.debug(
                            "match_auto_match_early_stop",
                            extra={
                                "store": store_key,
                                "query": query,
                                "scrape_ms": round(scrape_ms, 1),
                                "confidence": str(hit.confidence),
                            },
                        )
                        break

                if store_matched:
                    break

            store_elapsed_ms = (time.perf_counter() - store_t0) * 1000
            store_timing = {
                "store": store_key,
                "elapsed_ms": round(store_elapsed_ms, 1),
                "search_ms": round(search_ms_total, 1),
                "scrape_ms": round(scrape_ms_total, 1),
                "candidates_seen": candidates_seen,
                "title_rejects": title_rejects,
                "scrapes": scrapes_done,
                "matched": store_matched,
            }
            store_stage_ms[store_key] = store_timing
            logger.info("match_store_timing", extra=store_timing)
            observe(
                "product_match_store",
                store_elapsed_ms,
                category=OperationCategory.PRODUCT_MATCH,
                stage=store_key,
                context=store_timing,
            )

            if store_key in best_by_store:
                matches.append(best_by_store[store_key])
                emit(
                    type="matched",
                    store=store_key,
                    display_name=display_name,
                    stage="matched",
                    status="success",
                    message=f"Match em {store_key}",
                )
            else:
                unmatched.append(store_key)
                # Prefer search-level errors; otherwise surface scrape failures
                # so UPSTREAM_BLOCKED / RATE_LIMITED never look like NO_MATCH.
                if last_error is not None:
                    errors.append(last_error)
                    emit(
                        type="error",
                        store=store_key,
                        display_name=display_name,
                        stage="error",
                        status="error",
                        message=last_error.message,
                    )
                elif (
                    scrapes_done > 0
                    and scrape_failures >= scrapes_done
                    and last_scrape_error is not None
                ):
                    errors.append(last_scrape_error)
                    emit(
                        type="error",
                        store=store_key,
                        display_name=display_name,
                        stage="error",
                        status="error",
                        message=last_scrape_error.message,
                    )
                else:
                    emit(
                        type="no_match",
                        store=store_key,
                        display_name=display_name,
                        stage="no_match",
                        status="no_result",
                        message=f"Sem correspondência em {store_key}",
                    )

        match_elapsed_ms = (time.perf_counter() - match_t0) * 1000
        total_extra = {
            "elapsed_ms": round(match_elapsed_ms, 1),
            "stores": len(target_stores),
            "matches": len(matches),
            "stores_timing": {
                key: {
                    "elapsed_ms": val["elapsed_ms"],
                    "search_ms": val["search_ms"],
                    "scrape_ms": val["scrape_ms"],
                    "scrapes": val["scrapes"],
                    "matched": val["matched"],
                }
                for key, val in store_stage_ms.items()
            },
        }
        logger.info("match_total_timing", extra=total_extra)
        summary = format_stage_summary(
            "Product Match",
            match_elapsed_ms,
            {
                store: {
                    "elapsed_ms": timing["elapsed_ms"],
                    "search_ms": timing["search_ms"],
                    "scrape_ms": timing["scrape_ms"],
                    "scrapes": timing["scrapes"],
                    "matched": timing["matched"],
                }
                for store, timing in store_stage_ms.items()
            },
        )
        logger.info("match_timing_summary\n%s", summary)
        observe(
            "product_match",
            match_elapsed_ms,
            category=OperationCategory.PRODUCT_MATCH,
            stage="total",
            context=total_extra,
        )
        dup_tracker.observe_if_repeated(
            operation="product_match_duplicate_scrape",
            category=OperationCategory.PRODUCT_MATCH,
        )

        # Final consensus across all auto-matches (guards mid-flight conflicts).
        trusted = resolve_trusted_gtin(ref_identity, matches)
        if trusted is None and learned and learned.source == "reference":
            trusted = learned
        elif trusted is not None:
            learned = trusted

        if learned and learned.source != "reference" and not reference.gtin:
            reference = reference.model_copy(update={"gtin": learned.gtin})

        canonical_id = None
        if persist:
            if self._session is None:
                raise RequestError(
                    "Persistência requer DATABASE_URL / sessão SQLAlchemy",
                    code="DATABASE_UNAVAILABLE",
                )
            canonical_id = self._persist(reference, matches, learned)

        response = MatchResponse(
            canonical_product_id=canonical_id,
            reference=reference,
            matches=matches,
            unmatched_stores=unmatched,
            errors=errors,
            discovered_gtin=learned.gtin if learned else None,
            gtin_source=learned.source if learned else None,
        )
        emit(
            type="completed",
            stage="completed",
            status="success",
            message="Product Match concluído",
            result=response,
        )
        return response

    @staticmethod
    def _maybe_learn_gtin(
        current: TrustedGtin | None,
        reference_identity: object,
        hit: MatchHit,
    ) -> TrustedGtin | None:
        """Adopt a candidate GTIN mid-flight only under safe auto_match rules."""
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
    ) -> tuple[ProductPriceItem | None, MatchStoreError | None]:
        """Scrape a SERP candidate; wait once on domain RATE_LIMITED."""
        try:
            return self._scrape.scrape(url, include_images=include_images), None
        except ParseError as exc:
            logger.info(
                "match_candidate_scrape_failed",
                extra={"store": store_key, "url": url, "error": str(exc)},
            )
            return None, MatchStoreError(
                store=store_key,
                code="PARSE_ERROR",
                message=str(exc),
            )
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
                return None, MatchStoreError(
                    store=store_key,
                    code=exc.code,
                    message=str(exc),
                )
            wait = float(exc.retry_after or 15)
            wait = min(max(wait, 0.5), _MAX_RATE_LIMIT_WAIT_SECONDS)
            logger.info(
                "match_candidate_rate_limited_retry",
                extra={"store": store_key, "url": url, "wait_s": wait},
            )
            time.sleep(wait)
            try:
                return self._scrape.scrape(url, include_images=include_images), None
            except RequestError as retry_exc:
                logger.info(
                    "match_candidate_scrape_failed",
                    extra={
                        "store": store_key,
                        "url": url,
                        "error": str(retry_exc),
                    },
                )
                return None, MatchStoreError(
                    store=store_key,
                    code=retry_exc.code,
                    message=str(retry_exc),
                )
            except ParseError as retry_exc:
                logger.info(
                    "match_candidate_scrape_failed",
                    extra={
                        "store": store_key,
                        "url": url,
                        "error": str(retry_exc),
                    },
                )
                return None, MatchStoreError(
                    store=store_key,
                    code="PARSE_ERROR",
                    message=str(retry_exc),
                )

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
            from scout_api.modules.monitoring.hooks import initialize_listing_schedule

            initialize_listing_schedule(
                ref_listing, checked_at=ref_offer.scraped_at or datetime.now(UTC)
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
            from scout_api.modules.monitoring.hooks import initialize_listing_schedule

            initialize_listing_schedule(
                listing, checked_at=offer.scraped_at or datetime.now(UTC)
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
        # All implemented catalog keys — search-unsupported stores still appear
        # as terminal ERROR (SEARCH_UNSUPPORTED), never silently omitted.
        available = (
            [key for key, config in STORE_CONFIGS.items() if config.implemented]
            or list(stores_supporting_search())
            or list(MVP_SEARCH_STORES)
        )
        if requested:
            selected = [s.strip().lower() for s in requested if s.strip()]
        else:
            selected = list(available)
        return order_stores_for_match(
            selected,
            reference_store=reference.store,
            reference_has_gtin=reference_has_gtin,
        )
