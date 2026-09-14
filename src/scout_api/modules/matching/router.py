"""HTTP routes for product matching and offer refresh."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from scout_api.core.config import get_settings
from scout_api.core.database import get_db_session
from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.schemas import CrawlErrorResponse
from scout_api.modules.matching.offer_refresh_service import OfferRefreshService
from scout_api.modules.matching.product_match_service import ProductMatchService
from scout_api.modules.matching.schemas import (
    MatchRequest,
    MatchResponse,
    OfferRefreshRequest,
    OfferRefreshResponse,
)

router = APIRouter(tags=["matching"])


def _optional_db_session() -> Generator[Session | None, None, None]:
    settings = get_settings()
    if not settings.database_url:
        yield None
        return
    yield from get_db_session()


def get_match_service(
    session: Annotated[Session | None, Depends(_optional_db_session)],
) -> ProductMatchService:
    return ProductMatchService(session=session)


def get_refresh_service(
    session: Annotated[Session | None, Depends(_optional_db_session)],
) -> OfferRefreshService:
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "DATABASE_URL não configurada",
                "retryable": False,
            },
        )
    return OfferRefreshService(session=session)


@router.post(
    "/match",
    response_model=MatchResponse,
    responses={
        401: {"model": CrawlErrorResponse},
        422: {"model": CrawlErrorResponse},
        429: {"model": CrawlErrorResponse},
        502: {"model": CrawlErrorResponse},
        503: {"model": CrawlErrorResponse},
    },
    status_code=status.HTTP_200_OK,
)
def match_product(
    payload: MatchRequest,
    service: Annotated[ProductMatchService, Depends(get_match_service)],
) -> MatchResponse:
    if payload.persist and get_settings().database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": (
                    "DATABASE_URL não configurada; "
                    "use persist=false ou configure o Postgres"
                ),
                "retryable": False,
            },
        )
    try:
        return service.match(payload)
    except RequestError as exc:
        raise HTTPException(
            status_code=_status_for_request_error(exc),
            detail={
                "code": exc.code,
                "message": str(exc),
                "url": exc.url,
                "upstream_status": exc.upstream_status,
                "retryable": exc.retryable,
                "retry_after": exc.retry_after,
            },
        ) from exc
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "PARSE_ERROR",
                "message": str(exc),
                "url": str(payload.reference_url),
                "retryable": False,
            },
        ) from exc


@router.post(
    "/offers/refresh",
    response_model=OfferRefreshResponse,
    responses={
        401: {"model": CrawlErrorResponse},
        422: {"model": CrawlErrorResponse},
        429: {"model": CrawlErrorResponse},
        502: {"model": CrawlErrorResponse},
        503: {"model": CrawlErrorResponse},
    },
    status_code=status.HTTP_200_OK,
)
def refresh_offers(
    payload: OfferRefreshRequest,
    service: Annotated[OfferRefreshService, Depends(get_refresh_service)],
) -> OfferRefreshResponse:
    if get_settings().database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "DATABASE_URL não configurada",
                "retryable": False,
            },
        )
    if (
        payload.canonical_product_id is None
        and not payload.listing_ids
        and not payload.urls
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_REQUEST",
                "message": "Informe canonical_product_id, listing_ids ou urls",
                "retryable": False,
            },
        )
    try:
        return service.refresh(payload)
    except RequestError as exc:
        raise HTTPException(
            status_code=_status_for_request_error(exc),
            detail={
                "code": exc.code,
                "message": str(exc),
                "url": exc.url,
                "upstream_status": exc.upstream_status,
                "retryable": exc.retryable,
                "retry_after": exc.retry_after,
            },
        ) from exc
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "PARSE_ERROR",
                "message": str(exc),
                "retryable": False,
            },
        ) from exc


def _status_for_request_error(exc: RequestError) -> int:
    if exc.code in {"DUPLICATE_REQUEST", "RATE_LIMITED"}:
        return status.HTTP_429_TOO_MANY_REQUESTS
    if exc.code in {"DATABASE_UNAVAILABLE"}:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if exc.code in {"INVALID_REQUEST", "UNSUPPORTED_STORE", "SEARCH_UNSUPPORTED"}:
        return status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code == "AUTH_REQUIRED":
        return status.HTTP_401_UNAUTHORIZED
    return status.HTTP_502_BAD_GATEWAY
