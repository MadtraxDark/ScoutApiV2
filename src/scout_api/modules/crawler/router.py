from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from .core.exceptions import ParseError, RequestError
from .models.product import ProductPriceItem
from .schemas import CrawlErrorResponse, CrawlRequest
from .services.product_scrape_service import ProductScrapeService

router = APIRouter(prefix="/crawl", tags=["crawler"])


def get_product_scrape_service() -> ProductScrapeService:
    return ProductScrapeService()


@router.post(
    "",
    response_model=ProductPriceItem,
    responses={
        422: {"model": CrawlErrorResponse},
        429: {"model": CrawlErrorResponse},
        502: {"model": CrawlErrorResponse},
    },
    status_code=status.HTTP_200_OK,
)
def crawl_product(
    payload: CrawlRequest,
    service: Annotated[ProductScrapeService, Depends(get_product_scrape_service)],
) -> ProductPriceItem:
    try:
        return service.scrape(str(payload.url))
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
                "url": str(payload.url),
                "retryable": False,
            },
        ) from exc


def _status_for_request_error(exc: RequestError) -> int:
    if exc.code in {"DUPLICATE_REQUEST", "RATE_LIMITED"}:
        return status.HTTP_429_TOO_MANY_REQUESTS
    return status.HTTP_502_BAD_GATEWAY
