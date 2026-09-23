"""Tests for durable Product Match runs (ADR 0036)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scout_api.core.database import Base
from scout_api.modules.auth.schemas import AuthenticatedPrincipal, UserRole
from scout_api.modules.matching import models as matching_models  # noqa: F401
from scout_api.modules.matching.match_run_claim import (
    claim_due_match_runs,
    heartbeat_claim,
    new_worker_id,
)
from scout_api.modules.matching.match_run_service import (
    MatchRunService,
    NotificationService,
    format_duration_hms,
    sanitize_error_message,
)
from scout_api.modules.matching.models import (
    CanonicalProduct,
    ProductMatchRun,
    StoreListing,
    UserNotification,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as sess:
        yield sess


def _principal(user_id: uuid.UUID | None = None) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        id=user_id or uuid.uuid4(),
        role=UserRole.USER,
        display_name="tester",
    )


def _product(
    session: Session, *, owner: uuid.UUID, store_product_id: str = "123"
) -> CanonicalProduct:
    product = CanonicalProduct(
        title="Samsung Galaxy S25 Ultra",
        brand="Samsung",
        model="S25 Ultra",
        owner_user_id=owner,
    )
    session.add(product)
    session.flush()
    listing = StoreListing(
        canonical_product_id=product.id,
        store="kabum",
        country="BR",
        product_id=store_product_id,
        url=f"https://www.kabum.com.br/produto/{store_product_id}",
        canonical_url=f"https://www.kabum.com.br/produto/{store_product_id}",
        match_decision="auto_match",
        confidence=1,
        status="active",
        title=product.title,
    )
    session.add(listing)
    session.flush()
    return product


def test_format_duration_hms() -> None:
    assert format_duration_hms(13_000) == "00:00:13"
    assert format_duration_hms(522_000) == "00:08:42"
    assert format_duration_hms(4_625_000) == "01:17:05"


def test_sanitize_error_message_redacts_secrets() -> None:
    msg = sanitize_error_message("failed Authorization: Bearer abc")
    assert msg is not None
    assert "Bearer" not in msg


def test_start_creates_pending_run(session: Session) -> None:
    principal = _principal()
    product = _product(session, owner=principal.id)
    service = MatchRunService(session)

    # Bypass ownership via patching get_product
    service._registration.get_product = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(id=product.id)
    )

    run, created = service.start(product.id, principal=principal)
    session.commit()
    assert created is True
    assert run.status == "pending"
    assert run.product_id == product.id
    assert run.reference_url


def test_duplicate_start_returns_same_run(session: Session) -> None:
    principal = _principal()
    product = _product(session, owner=principal.id)
    service = MatchRunService(session)
    service._registration.get_product = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(id=product.id)
    )

    first, created1 = service.start(product.id, principal=principal)
    session.commit()
    second, created2 = service.start(product.id, principal=principal)
    session.commit()
    assert created1 is True
    assert created2 is False
    assert first.id == second.id


def test_active_run_endpoint_semantics(session: Session) -> None:
    principal = _principal()
    product = _product(session, owner=principal.id)
    service = MatchRunService(session)
    service._registration.get_product = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(id=product.id)
    )
    assert service.get_active(product.id, principal=principal) is None
    run, _ = service.start(product.id, principal=principal)
    session.commit()
    active = service.get_active(product.id, principal=principal)
    assert active is not None
    assert active.id == run.id


def test_different_products_can_have_active_runs(session: Session) -> None:
    principal = _principal()
    a = _product(session, owner=principal.id, store_product_id="111")
    b = _product(session, owner=principal.id, store_product_id="222")
    service = MatchRunService(session)
    service._registration.get_product = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda pid, viewer=None: MagicMock(id=pid)
    )
    run_a, _ = service.start(a.id, principal=principal)
    run_b, _ = service.start(b.id, principal=principal)
    session.commit()
    assert run_a.id != run_b.id
    assert run_a.status == "pending"
    assert run_b.status == "pending"


def test_claim_and_heartbeat(session: Session) -> None:
    principal = _principal()
    product = _product(session, owner=principal.id)
    run = ProductMatchRun(
        product_id=product.id,
        status="pending",
        requested_by=principal.id,
        reference_url="https://example.com/p",
        started_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
    )
    session.add(run)
    session.commit()

    worker = new_worker_id()
    claimed = claim_due_match_runs(session, worker_id=worker, limit=1)
    session.commit()
    assert len(claimed) == 1
    assert claimed[0].status == "running"
    assert claimed[0].worker_id == worker

    ok = heartbeat_claim(session, claimed[0], worker_id=worker)
    session.commit()
    assert ok is True


def test_stale_lease_reclaim(session: Session) -> None:
    principal = _principal()
    product = _product(session, owner=principal.id)
    now = datetime.now(UTC)
    run = ProductMatchRun(
        product_id=product.id,
        status="running",
        requested_by=principal.id,
        reference_url="https://example.com/p",
        started_at=now - timedelta(minutes=30),
        last_activity_at=now - timedelta(minutes=20),
        claimed_at=now - timedelta(minutes=20),
        claim_expires_at=now - timedelta(minutes=5),
        worker_id="dead-worker",
        attempts=1,
    )
    session.add(run)
    session.commit()

    claimed = claim_due_match_runs(session, worker_id="new-worker", limit=1)
    session.commit()
    assert len(claimed) == 1
    assert claimed[0].worker_id == "new-worker"
    assert claimed[0].attempts == 2


def test_notification_idempotent_on_complete(session: Session) -> None:
    principal = _principal()
    product = _product(session, owner=principal.id)
    run = ProductMatchRun(
        product_id=product.id,
        status="running",
        requested_by=principal.id,
        reference_url="https://example.com/p",
        started_at=datetime.now(UTC) - timedelta(minutes=3),
        last_activity_at=datetime.now(UTC),
        stores_total=2,
        stores_completed=2,
        matches_found=1,
    )
    session.add(run)
    session.flush()
    service = MatchRunService(session)
    n1 = service.finalize_completed(
        run,
        matches_found=1,
        no_matches=1,
        errors=0,
        stores_total=2,
        stores_completed=2,
    )
    session.commit()
    # Second finalize should not create a second notification of same type.
    run.status = "running"
    n2 = service.finalize_completed(
        run,
        matches_found=1,
        no_matches=1,
        errors=0,
        stores_total=2,
        stores_completed=2,
    )
    session.commit()
    assert n1 is not None
    assert n2 is not None
    assert n1.id == n2.id
    count = session.query(UserNotification).count()
    assert count == 1


def test_notification_unread_and_mark_read(session: Session) -> None:
    user_id = uuid.uuid4()
    row = UserNotification(
        user_id=user_id,
        type="PRODUCT_MATCH_COMPLETED",
        title="Busca concluída",
        message="ok",
        metadata_json={},
    )
    session.add(row)
    session.commit()
    service = NotificationService(session)
    assert service.unread_count(user_id) == 1
    service.mark_read(row.id, user_id=user_id)
    session.commit()
    assert service.unread_count(user_id) == 0


def test_select_reference_url_prefers_reliable_store(session: Session) -> None:
    from scout_api.modules.matching.match_run_service import (
        select_reference_url_for_product,
    )

    principal = _principal()
    product = CanonicalProduct(
        title="Samsung Galaxy S25 Ultra 256GB",
        brand="Samsung",
        model="Galaxy S25 Ultra",
        owner_user_id=principal.id,
    )
    session.add(product)
    session.flush()
    session.add(
        StoreListing(
            canonical_product_id=product.id,
            store="shoppingchina",
            country="PY",
            product_id="sc-1",
            url="https://www.shoppingchina.com.py/producto/a",
            canonical_url="https://www.shoppingchina.com.py/producto/a",
            match_decision="auto_match",
            confidence=1,
            status="active",
            title=product.title,
        )
    )
    session.add(
        StoreListing(
            canonical_product_id=product.id,
            store="kabum",
            country="BR",
            product_id="703054",
            url="https://www.kabum.com.br/produto/703054",
            canonical_url="https://www.kabum.com.br/produto/703054",
            match_decision="auto_match",
            confidence=1,
            status="active",
            title=product.title,
        )
    )
    session.commit()
    url = select_reference_url_for_product(session, product.id)
    assert url is not None
    assert "kabum.com.br" in url


def test_process_claimed_run_commits_before_match_and_persists_outcome(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Worker must not hold product_match_runs row lock during long match."""
    from scout_api.core.config import Settings
    from scout_api.modules.matching import match_run_worker as worker_mod
    from scout_api.modules.matching.identity import identity_reference_item
    from scout_api.modules.matching.match_run_worker import process_claimed_run
    from scout_api.modules.matching.models import MatchStoreRun
    from scout_api.modules.matching.schemas import MatchResponse

    principal = _principal()
    product = _product(session, owner=principal.id)
    run = ProductMatchRun(
        product_id=product.id,
        status="running",
        requested_by=principal.id,
        reference_url="https://www.kabum.com.br/produto/123",
        started_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
        worker_id="test-worker",
        attempts=1,
    )
    session.add(run)
    session.commit()
    run_id = run.id
    bind = session.get_bind()

    def fake_execute(
        sess: Session,
        *,
        run_id: object,
        product_id: object,
        reference_url: str,
        on_store_outcome: object,
    ) -> MatchResponse:
        del sess, product_id, reference_url, run_id
        on_store_outcome(  # type: ignore[operator]
            worker_mod.MatchStoreOutcome(
                store="amazon",
                display_name="Amazon",
                status="match",
                duration_ms=100,
                queries=("Samsung Galaxy S25 Ultra 256GB",),
                candidates_found=1,
                candidates_evaluated=1,
                search_duration_ms=50,
                candidate_fetch_duration_ms=40,
                matched_url="https://www.amazon.com.br/dp/B0DSYJCY45",
                matched_title="Samsung Galaxy S25 Ultra",
            )
        )
        reference = identity_reference_item(
            "Samsung Galaxy S25 Ultra",
            brand="Samsung",
            model="Galaxy S25 Ultra",
        )
        return MatchResponse(
            reference=reference,
            matches=[],
            unmatched_stores=[],
            errors=[],
        )

    def _factory() -> Session:
        return sessionmaker(bind=bind, expire_on_commit=False)()

    monkeypatch.setattr(worker_mod, "_execute_match_for_run", fake_execute)
    monkeypatch.setattr(worker_mod, "get_session_factory", lambda: _factory)

    settings = Settings(
        match_run_worker_enabled=True,
        match_run_lease_seconds=600,
        match_run_max_attempts=3,
    )
    row = session.get(ProductMatchRun, run_id)
    assert row is not None
    process_claimed_run(session, row, worker_id="test-worker", settings=settings)
    session.commit()

    fresh = session.get(ProductMatchRun, run_id)
    assert fresh is not None
    assert fresh.status == "completed"
    store_runs = list(session.query(MatchStoreRun).filter_by(run_id=run_id).all())
    assert len(store_runs) == 1
    assert store_runs[0].status == "match"
