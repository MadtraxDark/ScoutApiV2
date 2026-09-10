"""HTML fetch strategies for product pages.

Spiders only parse ``HtmlResponse``; fetchers own upstream access and WAF waits.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from scrapy.http import HtmlResponse, Request

from ..core.exceptions import RequestError

logger = logging.getLogger(__name__)

BrowserFactory = Callable[..., AbstractContextManager[Any]]


class HtmlFetcher(Protocol):
    def fetch(self, url: str) -> HtmlResponse:
        """Return a Scrapy response ready for ``parse_product``."""


def is_challenge_page(html: str, *, title: str | None = None) -> bool:
    """Detect Cloudflare / Akamai interstitial pages that are not product HTML."""
    title_text = (title or "").strip().lower()
    if "just a moment" in title_text:
        return True
    lower = html.lower()
    if "akamai-bot" in lower and (
        "não é possível acessar" in lower or "nao e possivel acessar" in lower
    ):
        return True
    if "performing security verification" in lower and len(html) < 80_000:
        return True
    if re.search(r"cf-challenge|challenge-platform", lower) and len(html) < 40_000:
        return True
    return False


class UrllibHtmlFetcher:
    """Lightweight HTTP fetch for stores without a hard WAF (tests / fallback)."""

    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urlopen,
        user_agent: str,
        timeout: int = 30,
    ) -> None:
        self._opener = opener
        self._user_agent = user_agent
        self._timeout = timeout

    def fetch(self, url: str) -> HtmlResponse:
        request = UrlRequest(url, headers={"User-Agent": self._user_agent})
        try:
            with self._opener(request, timeout=self._timeout) as upstream:
                body = upstream.read()
                status = int(getattr(upstream, "status", 200))
                content_type = upstream.headers.get("Content-Type", "")
                charset = upstream.headers.get_content_charset() or "utf-8"
                if status >= 400:
                    raise RequestError(
                        f"A loja recusou a requisição (HTTP {status})",
                        code="UPSTREAM_BLOCKED"
                        if status in (403, 429)
                        else "UPSTREAM_HTTP_ERROR",
                        url=url,
                        upstream_status=status,
                        retryable=status == 429,
                    )
                text = body.decode(charset, errors="replace")
                if is_challenge_page(text):
                    raise RequestError(
                        "A loja bloqueou a requisição (desafio anti-bot)",
                        code="UPSTREAM_BLOCKED",
                        url=url,
                        upstream_status=403,
                        retryable=True,
                    )
                return HtmlResponse(
                    url=url,
                    status=status,
                    headers={"Content-Type": content_type},
                    body=body,
                    encoding=charset,
                    request=Request(url),
                )
        except RequestError:
            raise
        except HTTPError as exc:
            raise RequestError(
                "A loja recusou a requisição",
                code="UPSTREAM_BLOCKED"
                if exc.code in (403, 429)
                else "UPSTREAM_HTTP_ERROR",
                url=url,
                upstream_status=exc.code,
                retryable=exc.code == 429,
            ) from exc
        except URLError as exc:
            raise RequestError(
                "Não foi possível conectar à loja",
                code="UPSTREAM_NETWORK_ERROR",
                url=url,
                retryable=True,
            ) from exc
        except OSError as exc:
            raise RequestError(
                "Falha local ao acessar a loja",
                code="UPSTREAM_REQUEST_ERROR",
                url=url,
                retryable=False,
            ) from exc


class CamoufoxHtmlFetcher:
    """Fetch product HTML with Camoufox (Firefox patched for anti-bot)."""

    def __init__(
        self,
        *,
        headless: bool = True,
        humanize: bool = True,
        timeout_ms: int = 90_000,
        settle_ms: int = 5_000,
        max_settle_attempts: int = 12,
        browser_factory: BrowserFactory | None = None,
    ) -> None:
        self._headless = headless
        self._humanize = humanize
        self._timeout_ms = timeout_ms
        self._settle_ms = settle_ms
        self._max_settle_attempts = max_settle_attempts
        self._browser_factory = browser_factory

    def fetch(self, url: str) -> HtmlResponse:
        try:
            with self._open_browser() as browser:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
                html, final_url, title = self._wait_for_product_html(page)
                if is_challenge_page(html, title=title):
                    raise RequestError(
                        "A loja bloqueou a requisição (desafio anti-bot)",
                        code="UPSTREAM_BLOCKED",
                        url=final_url or url,
                        upstream_status=403,
                        retryable=True,
                    )
                body = html.encode("utf-8")
                return HtmlResponse(
                    url=final_url or url,
                    status=200,
                    headers={"Content-Type": "text/html; charset=utf-8"},
                    body=body,
                    encoding="utf-8",
                    request=Request(url),
                )
        except RequestError:
            raise
        except Exception as exc:
            logger.exception("camoufox_fetch_failed", extra={"url": url})
            raise RequestError(
                "Falha ao renderizar a página com Camoufox",
                code="UPSTREAM_REQUEST_ERROR",
                url=url,
                retryable=True,
            ) from exc

    def _open_browser(self) -> AbstractContextManager[Any]:
        if self._browser_factory is not None:
            return self._browser_factory(
                headless=self._headless, humanize=self._humanize
            )
        from camoufox.sync_api import Camoufox

        return Camoufox(  # type: ignore[no-untyped-call]
            headless=self._headless, humanize=self._humanize
        )

    def _wait_for_product_html(self, page: Any) -> tuple[str, str, str]:
        html = ""
        final_url = ""
        title = ""
        for attempt in range(max(1, self._max_settle_attempts)):
            if attempt > 0:
                page.wait_for_timeout(self._settle_ms)
            html = page.content()
            final_url = str(page.url)
            try:
                title = str(page.title())
            except Exception:
                title = ""
            if not is_challenge_page(html, title=title):
                return html, final_url, title
            logger.info(
                "camoufox_waiting_challenge",
                extra={"url": final_url, "attempt": attempt + 1},
            )
        return html, final_url, title


def build_html_fetcher(
    *,
    camoufox_enabled: bool,
    user_agent: str,
    urllib_timeout: int = 30,
    camoufox_headless: bool = True,
    camoufox_humanize: bool = True,
    camoufox_timeout_ms: int = 90_000,
    camoufox_settle_ms: int = 5_000,
    camoufox_max_settle_attempts: int = 12,
) -> HtmlFetcher:
    if camoufox_enabled:
        return CamoufoxHtmlFetcher(
            headless=camoufox_headless,
            humanize=camoufox_humanize,
            timeout_ms=camoufox_timeout_ms,
            settle_ms=camoufox_settle_ms,
            max_settle_attempts=camoufox_max_settle_attempts,
        )
    return UrllibHtmlFetcher(user_agent=user_agent, timeout=urllib_timeout)
