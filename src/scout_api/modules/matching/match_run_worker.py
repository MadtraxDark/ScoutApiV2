"""Background Product Match run worker (PostgreSQL-backed durable queue)."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from scout_api.core.config import Settings, get_settings
from scout_api.core.database import get_session_factory
from scout_api.core.performance import OperationCategory, timed
from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.matching.identity import identity_reference_item
from scout_api.modules.matching.match_run_claim import (
    claim_due_match_runs,
    heartbeat_claim,
    new_worker_id,
    utcnow,
)
from scout_api.modules.matching.match_run_service import MatchRunService
from scout_api.modules.matching.models import CanonicalProduct, ProductMatchRun
from scout_api.modules.matching.product_match_service import (
    MatchStoreOutcome,
    ProductMatchService,
)
from scout_api.modules.matching.schemas import MatchRequest, MatchResponse

logger = logging.getLogger(__name__)

_STOP = False
_scheduler_lock = threading.Lock()
_scheduler: MatchRunScheduler | None = None


def _handle_stop(_signum: int, _frame: object) -> None:
    global _STOP
    _STOP = True
    logger.info("match_run_worker_stop_requested")


def _fail_stale_exhausted(
    session: Session,
    run: ProductMatchRun,
    *,
    settings: Settings,
) -> bool:
    """Mark irrecoverable runs that exceeded max attempts after lease expiry."""
    max_attempts = max(1, int(settings.match_run_max_attempts))
    if int(run.attempts or 0) < max_attempts:
        return False
    if run.status not in ("pending", "running"):
        return False
    MatchRunService(session).finalize_failed(
        run,
        code="STALE_LEASE_EXHAUSTED",
        message=(
            "A busca foi interrompida e esgotou tentativas de recuperação. "
            "Inicie uma nova busca."
        ),
    )
    return True


def _reference_from_canonical(product: CanonicalProduct) -> object:
    """Build identity-only reference when live reference scrape fails."""
    attrs = dict(product.attributes or {})
    variant = attrs.get("variant")
    category = attrs.get("category")
    return identity_reference_item(
        product.title or "",
        brand=product.brand,
        model=product.model,
        variant=str(variant) if variant else None,
        category=str(category) if category else None,
    )


def _execute_match_for_run(
    session: Session,
    *,
    run_id: object,
    product_id: object,
    reference_url: str,
    on_store_outcome: Any,
) -> MatchResponse:
    """Scrape reference URL; on failure, fall back to canonical identity."""
    match_service = ProductMatchService(session=session)
    request = MatchRequest(
        reference_url=reference_url,  # type: ignore[arg-type]
        canonical_product_id=product_id,  # type: ignore[arg-type]
        persist=True,
        include_review=True,
        include_images=False,
    )
    try:
        return match_service.match(request, on_store_outcome=on_store_outcome)
    except RequestError as exc:
        product = session.get(CanonicalProduct, product_id)
        title = (product.title or "").strip() if product is not None else ""
        if not title:
            raise
        logger.warning(
            "match_run_reference_fallback",
            extra={
                "run_id": str(run_id),
                "product_id": str(product_id),
                "code": exc.code,
            },
        )
        reference = _reference_from_canonical(product)
        return match_service.match_from_item(
            reference,  # type: ignore[arg-type]
            persist=True,
            include_review=True,
            include_images=False,
            canonical_product_id=product_id,  # type: ignore[arg-type]
            on_store_outcome=on_store_outcome,
        )


def process_claimed_run(
    session: Session,
    run: ProductMatchRun,
    *,
    worker_id: str,
    settings: Settings,
) -> ProductMatchRun:
    """Execute one claimed match run; never raises — status is persisted."""
    run_id = run.id
    product_id = run.product_id
    reference_url = run.reference_url
    started = utcnow()
    service = MatchRunService(session)

    if _fail_stale_exhausted(session, run, settings=settings):
        session.flush()
        return run

    if not reference_url:
        service.finalize_failed(
            run,
            code="REFERENCE_URL_MISSING",
            message="Produto sem URL de referência para busca.",
        )
        session.flush()
        return run

    # Claim already committed in sweep_once. Touch activity in a short
    # transaction, then RELEASE the row lock before the long match.
    # Holding product_match_runs locked during Camoufox/search blocks
    # on_store_outcome + heartbeat (statement_timeout → INTERNAL_ERROR).
    run.status = "running"
    run.last_activity_at = utcnow()
    session.commit()
    session.expunge_all()

    stop_heartbeat = threading.Event()

    def _heartbeat_loop() -> None:
        interval = max(15, int(settings.match_run_lease_seconds) // 3)
        while not stop_heartbeat.wait(interval):
            try:
                factory = get_session_factory()
                with factory() as hb_session:
                    row = hb_session.get(ProductMatchRun, run_id)
                    if row is None or row.status != "running":
                        return
                    ok = heartbeat_claim(
                        hb_session, row, worker_id=worker_id, settings=settings
                    )
                    hb_session.commit()
                    if not ok:
                        return
            except Exception:  # noqa: BLE001
                logger.exception("match_run_heartbeat_failed run_id=%s", run_id)

    hb_thread = threading.Thread(
        target=_heartbeat_loop, name=f"match-hb-{run_id.hex[:8]}", daemon=True
    )
    hb_thread.start()

    outcome_lock = threading.Lock()

    def on_store_outcome(outcome: MatchStoreOutcome) -> None:
        with outcome_lock:
            try:
                factory = get_session_factory()
                with factory() as store_session:
                    row = store_session.get(ProductMatchRun, run_id)
                    if row is None:
                        return
                    MatchRunService(store_session).apply_store_outcome(
                        row,
                        store=outcome.store,
                        display_name=outcome.display_name,
                        status=outcome.status,
                        duration_ms=outcome.duration_ms,
                        queries=list(outcome.queries),
                        candidates_found=outcome.candidates_found,
                        candidates_evaluated=outcome.candidates_evaluated,
                        matched_url=outcome.matched_url,
                        matched_title=outcome.matched_title,
                        matched_price=outcome.matched_price,
                        matched_currency=outcome.matched_currency,
                        matched_confidence=outcome.matched_confidence,
                        matched_reasons=list(outcome.matched_reasons),
                        error_code=outcome.error_code,
                        error_message=outcome.error_message,
                        search_duration_ms=outcome.search_duration_ms,
                        candidate_fetch_duration_ms=outcome.candidate_fetch_duration_ms,
                        candidates=[dict(c) for c in outcome.candidates],
                    )
                    store_session.commit()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "match_run_store_outcome_failed run_id=%s store=%s",
                    run_id,
                    outcome.store,
                )

    try:
        with timed(
            "product_match_run_job",
            category=OperationCategory.PRODUCT_MATCH,
            context={"run_id": str(run_id), "product_id": str(product_id)},
        ):
            response = _execute_match_for_run(
                session,
                run_id=run_id,
                product_id=product_id,
                reference_url=reference_url,
                on_store_outcome=on_store_outcome,
            )

        session.expire_all()
        fresh = session.get(ProductMatchRun, run_id)
        if fresh is None:
            return run
        matches_found = len(response.matches)
        no_matches = len(response.unmatched_stores)
        errors = len(response.errors)
        stores_total = matches_found + no_matches + errors
        service.finalize_completed(
            fresh,
            matches_found=matches_found,
            no_matches=no_matches,
            errors=errors,
            stores_total=max(stores_total, int(fresh.stores_completed or 0)),
            stores_completed=int(fresh.stores_completed or stores_total),
        )
        finished = utcnow()
        logger.info(
            "match_run_done",
            extra={
                "run_id": str(run_id),
                "product_id": str(product_id),
                "status": "completed",
                "started_at": started.isoformat(),
                "finished_at": finished.isoformat(),
                "duration_ms": int((finished - started).total_seconds() * 1000),
                "matches_found": matches_found,
                "no_matches": no_matches,
                "errors": errors,
            },
        )
        return fresh
    except RequestError as exc:
        fresh = session.get(ProductMatchRun, run_id)
        if fresh is None:
            return run
        service.finalize_failed(
            fresh, code=exc.code or "REQUEST_ERROR", message=str(exc)
        )
        return fresh
    except ParseError as exc:
        fresh = session.get(ProductMatchRun, run_id)
        if fresh is None:
            return run
        service.finalize_failed(fresh, code="PARSE_ERROR", message=str(exc))
        return fresh
    except Exception:  # noqa: BLE001
        logger.exception("match_run_failed run_id=%s", run_id)
        fresh = session.get(ProductMatchRun, run_id)
        if fresh is None:
            return run
        service.finalize_failed(
            fresh, code="INTERNAL_ERROR", message="Falha interna no Product Match"
        )
        return fresh
    finally:
        stop_heartbeat.set()
        hb_thread.join(timeout=2.0)


def sweep_once(
    session: Session,
    *,
    worker_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Claim due match runs and process them sequentially."""
    cfg = settings or get_settings()
    if not cfg.match_run_worker_enabled:
        return {"claimed": 0, "processed": 0, "duration_ms": 0, "skipped": True}

    started = time.perf_counter()
    claimed = claim_due_match_runs(session, worker_id=worker_id, settings=cfg)
    session.commit()

    processed = 0
    for run in claimed:
        row = session.get(ProductMatchRun, run.id)
        if row is None:
            continue
        process_claimed_run(session, row, worker_id=worker_id, settings=cfg)
        session.commit()
        processed += 1

    return {
        "claimed": len(claimed),
        "processed": processed,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


class MatchRunScheduler:
    """In-process poller used by the API lifespan (and tests)."""

    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_id = new_worker_id()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="match-run-scheduler", daemon=True
        )
        self._thread.start()
        logger.info(
            "match_run_scheduler_started",
            extra={"worker_id": self._worker_id},
        )

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("match_run_scheduler_stopped")

    def _loop(self) -> None:
        interval = max(1.0, float(self._settings.match_run_sweep_interval_seconds))
        while not self._stop.is_set():
            try:
                if self._settings.database_url:
                    factory = get_session_factory()
                    with factory() as session:
                        sweep_once(
                            session, worker_id=self._worker_id, settings=self._settings
                        )
            except Exception:  # noqa: BLE001
                logger.exception("match_run_scheduler_sweep_failed")
            self._stop.wait(interval)


def start_scheduler(*, settings: Settings | None = None) -> MatchRunScheduler | None:
    global _scheduler
    cfg = settings or get_settings()
    if not cfg.match_run_worker_enabled:
        return None
    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = MatchRunScheduler(settings=cfg)
            _scheduler.start()
        return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            _scheduler.stop()
            _scheduler = None


def run_forever(*, settings: Settings | None = None) -> None:
    global _STOP
    cfg = settings or get_settings()
    worker_id = new_worker_id()
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    logger.info("match_run_worker_started", extra={"worker_id": worker_id})
    interval = max(1.0, float(cfg.match_run_sweep_interval_seconds))
    while not _STOP:
        try:
            factory = get_session_factory()
            with factory() as session:
                sweep_once(session, worker_id=worker_id, settings=cfg)
        except Exception:  # noqa: BLE001
            logger.exception("match_run_worker_sweep_failed")
        time.sleep(interval)
    logger.info("match_run_worker_stopped", extra={"worker_id": worker_id})


def main() -> None:
    parser = argparse.ArgumentParser(description="ScoutApiV2 product match run worker")
    parser.parse_args()
    run_forever()


if __name__ == "__main__":
    main()
