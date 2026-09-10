import logging
from typing import Any

from scrapy import signals
from scrapy.http import Request, Response

from .core.retry import backoff_delay, retry_after

logger = logging.getLogger(__name__)


class PoliteRetryMiddleware:
    """Bounded retry with jitter and Retry-After support for transient failures."""

    transient = {408, 429, 500, 502, 503, 504}

    def process_response(
        self, request: Request, response: Response, spider: Any
    ) -> Response | Request:
        if response.status not in self.transient:
            return response
        retries = int(request.meta.get("retry_count", 0))
        maximum = int(spider.settings.getint("RETRY_TIMES", 3))
        if retries >= maximum:
            return response
        header = response.headers.get("Retry-After") or b""
        delay = retry_after(header.decode()) or backoff_delay(retries)
        retry = request.copy()
        retry.meta["retry_count"] = retries + 1
        retry.meta["download_delay_override"] = delay
        logger.info(
            "retry_scheduled",
            extra={
                "store": getattr(spider, "store", "unknown"),
                "attempt": retries + 1,
                "status": response.status,
                "delay": delay,
            },
        )
        return retry

    def process_exception(
        self, request: Request, exception: Exception, spider: Any
    ) -> Request | None:
        retries = int(request.meta.get("retry_count", 0))
        maximum = int(spider.settings.getint("RETRY_TIMES", 3))
        if retries >= maximum:
            return None
        retry = request.copy()
        retry.meta["retry_count"] = retries + 1
        retry.meta["download_delay_override"] = backoff_delay(retries)
        return retry

    @classmethod
    def from_crawler(cls, crawler: Any) -> "PoliteRetryMiddleware":
        middleware = cls()
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        return middleware

    def spider_opened(self, spider: Any) -> None:
        logger.info(
            "crawler_started", extra={"store": getattr(spider, "store", "unknown")}
        )
