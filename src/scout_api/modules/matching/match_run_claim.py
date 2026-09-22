"""Claim due Product Match runs with lease + SKIP LOCKED (PostgreSQL)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, or_, select, update
from sqlalchemy.orm import Session

from scout_api.core.config import Settings, get_settings
from scout_api.modules.matching.models import ProductMatchRun

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("pending", "running")


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_worker_id() -> str:
    return uuid.uuid4().hex[:16]


def _due_filter(*, now: datetime) -> object:
    """Pending never claimed, or running/pending with expired lease."""
    lease_expired = or_(
        ProductMatchRun.claim_expires_at.is_(None),
        ProductMatchRun.claim_expires_at <= now,
    )
    pending_unclaimed = and_(
        ProductMatchRun.status == "pending",
        lease_expired,
    )
    # Stale RUNNING with expired lease → recoverable by another worker.
    stale_running = and_(
        ProductMatchRun.status == "running",
        lease_expired,
    )
    return or_(pending_unclaimed, stale_running)


def claim_due_match_runs(
    session: Session,
    *,
    worker_id: str,
    limit: int | None = None,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> list[ProductMatchRun]:
    """Atomically claim up to ``limit`` match runs needing execution."""
    cfg = settings or get_settings()
    moment = now or utcnow()
    batch = max(1, int(limit or cfg.match_run_batch_size))
    lease = timedelta(seconds=max(60, int(cfg.match_run_lease_seconds)))
    claim_expires = moment + lease

    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return _claim_postgres(
            session,
            worker_id=worker_id,
            batch=batch,
            now=moment,
            claim_expires=claim_expires,
        )
    return _claim_portable(
        session,
        worker_id=worker_id,
        batch=batch,
        now=moment,
        claim_expires=claim_expires,
    )


def _claim_postgres(
    session: Session,
    *,
    worker_id: str,
    batch: int,
    now: datetime,
    claim_expires: datetime,
) -> list[ProductMatchRun]:
    stmt: Select[tuple[ProductMatchRun]] = (
        select(ProductMatchRun)
        .where(_due_filter(now=now))
        .order_by(ProductMatchRun.started_at.asc())
        .limit(batch)
        .with_for_update(skip_locked=True)
    )
    rows = list(session.scalars(stmt).all())
    claimed: list[ProductMatchRun] = []
    for run in rows:
        run.status = "running"
        run.attempts = int(run.attempts or 0) + 1
        run.claimed_at = now
        run.claim_expires_at = claim_expires
        run.worker_id = worker_id
        run.last_activity_at = now
        if run.started_at is None:
            run.started_at = now
        claimed.append(run)
    if claimed:
        session.flush()
    return claimed


def _claim_portable(
    session: Session,
    *,
    worker_id: str,
    batch: int,
    now: datetime,
    claim_expires: datetime,
) -> list[ProductMatchRun]:
    """Optimistic claim for SQLite tests (no SKIP LOCKED)."""
    stmt = (
        select(ProductMatchRun)
        .where(_due_filter(now=now))
        .order_by(ProductMatchRun.started_at.asc())
        .limit(batch)
    )
    rows = list(session.scalars(stmt).all())
    claimed: list[ProductMatchRun] = []
    for run in rows:
        result = session.execute(
            update(ProductMatchRun)
            .where(
                ProductMatchRun.id == run.id,
                _due_filter(now=now),
            )
            .values(
                status="running",
                attempts=int(run.attempts or 0) + 1,
                claimed_at=now,
                claim_expires_at=claim_expires,
                worker_id=worker_id,
                last_activity_at=now,
            )
        )
        if result.rowcount:
            session.refresh(run)
            claimed.append(run)
    return claimed


def heartbeat_claim(
    session: Session,
    run: ProductMatchRun,
    *,
    worker_id: str,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> bool:
    """Extend lease while the match is still running. Returns False if lost."""
    cfg = settings or get_settings()
    moment = now or utcnow()
    lease = timedelta(seconds=max(60, int(cfg.match_run_lease_seconds)))
    claim_expires = moment + lease
    result = session.execute(
        update(ProductMatchRun)
        .where(
            ProductMatchRun.id == run.id,
            ProductMatchRun.worker_id == worker_id,
            ProductMatchRun.status == "running",
        )
        .values(
            claim_expires_at=claim_expires,
            last_activity_at=moment,
        )
    )
    if result.rowcount:
        run.claim_expires_at = claim_expires
        run.last_activity_at = moment
        return True
    return False


def release_claim(run: ProductMatchRun) -> None:
    run.worker_id = None
    run.claimed_at = None
    run.claim_expires_at = None
