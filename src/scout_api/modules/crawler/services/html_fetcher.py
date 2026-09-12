"""HTML fetch strategies for product pages.

Spiders only parse ``HtmlResponse``; fetchers own upstream access and WAF waits.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from scrapy.http import HtmlResponse, Request

from ..core.exceptions import RequestError

logger = logging.getLogger(__name__)

BrowserFactory = Callable[..., AbstractContextManager[Any]]


class HtmlFetcher(Protocol):
    def fetch(self, url: str) -> HtmlResponse:
        """Return a Scrapy response ready for ``parse_product``."""


def is_hard_block_page(html: str, *, title: str | None = None) -> bool:
    """Detect Cloudflare / WAF hard bans (IP block), not solvable JS challenges."""
    title_text = (title or "").strip().lower()
    if "attention required" in title_text:
        return True
    lower = html.lower()
    return "you have been blocked" in lower or "sorry, you have been blocked" in lower


def is_challenge_page(html: str, *, title: str | None = None) -> bool:
    """Detect Cloudflare / Akamai interstitial pages that are not product HTML."""
    if is_hard_block_page(html, title=title):
        return True
    title_text = (title or "").strip().lower()
    if title_text.startswith("loading "):
        return True
    if "just a moment" in title_text or "un momento" in title_text:
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


def locale_for_url(url: str) -> str | None:
    """Prefer store-local locale so Intl/fingerprint match the target site."""
    hostname = (urlparse(url).hostname or "").lower()
    if hostname == "nissei.com" or hostname.endswith(".nissei.com"):
        return "es-PY"
    if hostname == "magazineluiza.com.br" or hostname.endswith(".magazineluiza.com.br"):
        return "pt-BR"
    if hostname == "shopee.com.br" or hostname.endswith(".shopee.com.br"):
        return "pt-BR"
    return None


def warmup_url_for(url: str) -> str | None:
    """Origin warm-up URL used to mint Cloudflare cookies before the product page."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if not hostname or not parsed.scheme:
        return None
    if hostname == "nissei.com" or hostname.endswith(".nissei.com"):
        return f"{parsed.scheme}://{parsed.netloc}/py/"
    if hostname == "shopee.com.br" or hostname.endswith(".shopee.com.br"):
        return f"{parsed.scheme}://{parsed.netloc}/"
    return None


_SHOPEE_ITEM_PATH = re.compile(
    r"[.-]i\.(?P<shop_id>\d+)\.(?P<item_id>\d+)",
    re.IGNORECASE,
)


def shopee_ids_from_url(url: str) -> tuple[str, str] | None:
    """Extract shop_id / item_id from a Shopee product URL path."""
    path = urlparse(url).path or ""
    match = _SHOPEE_ITEM_PATH.search(path)
    if not match:
        return None
    return match.group("shop_id"), match.group("item_id")


def looks_like_shopee_pdp(html: str) -> bool:
    """True when HTML/JSON already carries a Shopee item payload."""
    head = (html or "")[:20_000]
    return '"item"' in head and (
        '"item_id"' in head or '"itemid"' in head or '"models"' in head
    )


def is_shopee_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname == "shopee.com.br" or hostname.endswith(".shopee.com.br")


def is_shopee_traffic_block(url: str, html: str = "") -> bool:
    """Shopee anti-fraud interstitial (verify/traffic), not a product page."""
    folded_url = (url or "").casefold()
    folded_html = (html or "")[:8_000].casefold()
    return "/verify/traffic" in folded_url or "verify/traff" in folded_html


def wrap_shopee_pdp_json(raw: str) -> str:
    """Embed a captured get_pc JSON body so spiders parse a normal HtmlResponse."""
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        "<title>Shopee PDP</title></head><body>"
        f'<script type="application/json" data-shopee-pdp="1">{raw}</script>'
        "</body></html>"
    )


def is_shopee_get_pc_url(url: str) -> bool:
    path = (urlparse(url).path or "").casefold()
    return "/api/v4/pdp/get_pc" in path or path.endswith("/api/v4/pdp/get")


def apply_shopee_br_proxy_targeting(proxy_url: str, page_url: str) -> str:
    """Pin DataImpulse-style username geo to Brazil for shopee.com.br."""
    if not proxy_url or not is_shopee_url(page_url):
        return proxy_url
    parsed = urlparse(proxy_url.strip())
    if not parsed.hostname or not parsed.username:
        return proxy_url
    username = unquote(parsed.username)
    if "__cr." in username:
        return proxy_url
    from urllib.parse import quote, urlunparse

    netloc = (
        f"{quote(username + '__cr.br', safe='')}"
        f":{quote(unquote(parsed.password or ''), safe='')}"
        f"@{parsed.hostname}"
    )
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def proxy_settings_from_url(proxy_url: str) -> dict[str, str]:
    """Convert ``http(s)://user:pass@host:port`` into Camoufox/Playwright proxy dict."""
    parsed = urlparse(proxy_url.strip())
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"Invalid proxy URL: {proxy_url!r}")
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port is not None:
        server = f"{server}:{parsed.port}"
    settings: dict[str, str] = {"server": server}
    if parsed.username:
        settings["username"] = unquote(parsed.username)
    if parsed.password:
        settings["password"] = unquote(parsed.password)
    return settings


def default_user_data_dir() -> Path:
    return Path.home() / ".cache" / "scout-api" / "camoufox-profiles" / "default"


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
        proxy_url: str | None = None,
        user_data_dir: str | Path | None = None,
        disable_coop: bool = True,
        warmup_origin: bool = True,
        browser_factory: BrowserFactory | None = None,
    ) -> None:
        self._headless = headless
        self._humanize = humanize
        self._timeout_ms = timeout_ms
        self._settle_ms = settle_ms
        self._max_settle_attempts = max_settle_attempts
        self._proxy_url = proxy_url
        if user_data_dir:
            self._user_data_dir = Path(user_data_dir)
        else:
            self._user_data_dir = default_user_data_dir()
        self._disable_coop = disable_coop
        self._warmup_origin = warmup_origin
        self._browser_factory = browser_factory
        self._lock = threading.Lock()

    def fetch(self, url: str) -> HtmlResponse:
        with self._lock:
            return self._fetch_locked(url)

    def _fetch_locked(self, url: str) -> HtmlResponse:
        try:
            with self._open_browser(url=url) as browser:
                page = self._new_page(browser)
                captured: dict[str, str] = {}
                if is_shopee_url(url):
                    self._attach_shopee_get_pc_listener(page, captured, url)
                if self._warmup_origin:
                    self._maybe_warmup(page, url)
                self._goto(page, url)
                html, final_url, title = self._wait_for_product_html(
                    page, captured=captured
                )
                if captured.get("body"):
                    html = wrap_shopee_pdp_json(captured["body"])
                    final_url = url
                    title = "Shopee PDP"
                    logger.info(
                        "shopee_get_pc_intercepted",
                        extra={"url": captured.get("response_url") or url},
                    )
                if is_shopee_traffic_block(final_url or url, html):
                    raise RequestError(
                        "Shopee bloqueou a requisição "
                        "(verificação de tráfego / anti-bot)",
                        code="UPSTREAM_BLOCKED",
                        url=final_url or url,
                        upstream_status=403,
                        retryable=True,
                    )
                if is_hard_block_page(html, title=title):
                    raise RequestError(
                        "A loja bloqueou o IP de saída (hard-block anti-bot); "
                        "configure um proxy residencial (CAMOUFOX_PROXY_URL)",
                        code="UPSTREAM_BLOCKED",
                        url=final_url or url,
                        upstream_status=403,
                        retryable=False,
                    )
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

    def _open_browser(self, *, url: str) -> AbstractContextManager[Any]:
        launch_kwargs = self._launch_kwargs(url=url)
        if self._browser_factory is not None:
            return self._browser_factory(**launch_kwargs)
        from camoufox.sync_api import Camoufox

        return Camoufox(**launch_kwargs)  # type: ignore[no-untyped-call]

    def _launch_kwargs(self, *, url: str) -> dict[str, Any]:
        # Linux Docker headless is detected by Cloudflare; Xvfb "virtual" passes.
        headless: bool | str = self._headless
        if self._headless is True and sys.platform.startswith("linux"):
            headless = "virtual"
        profile_dir = self._ensure_user_data_dir()
        kwargs: dict[str, Any] = {
            "headless": headless,
            "humanize": self._humanize,
            "os": "windows",
            "geoip": True,
            "persistent_context": True,
            "user_data_dir": str(profile_dir),
        }
        # uBlock triggers Shopee "automated tools" detection (Camoufox #345).
        try:
            from camoufox.addons import DefaultAddons

            kwargs["exclude_addons"] = [DefaultAddons.UBO]
        except Exception:
            logger.debug("camoufox_exclude_addons_unavailable", exc_info=True)
        if self._disable_coop:
            # Needed so Turnstile iframes are interactable; ack Camoufox leak warning.
            kwargs["disable_coop"] = True
            kwargs["i_know_what_im_doing"] = True
        if self._proxy_url:
            proxy_url = apply_shopee_br_proxy_targeting(self._proxy_url, url)
            kwargs["proxy"] = proxy_settings_from_url(proxy_url)
            # Some HTTP residential proxies break Camoufox's geoip IP probe (SSL to
            # ipecho/etc). Keep residential egress; pin locale from the store URL.
            kwargs["geoip"] = False
            locale = locale_for_url(url)
            if locale is not None:
                kwargs["locale"] = locale
        else:
            locale = locale_for_url(url)
            if locale is not None:
                kwargs["locale"] = locale
        return kwargs

    def _ensure_user_data_dir(self) -> Path:
        try:
            self._user_data_dir.mkdir(parents=True, exist_ok=True)
            return self._user_data_dir
        except OSError as exc:
            fallback = Path("/tmp/scout-api-camoufox-profiles/default")
            logger.warning(
                "camoufox_profile_dir_unwritable",
                extra={
                    "configured": str(self._user_data_dir),
                    "fallback": str(fallback),
                    "error": str(exc),
                },
            )
            fallback.mkdir(parents=True, exist_ok=True)
            self._user_data_dir = fallback
            return fallback

    @staticmethod
    def _new_page(browser: Any) -> Any:
        if hasattr(browser, "new_page"):
            return browser.new_page()
        pages = getattr(browser, "pages", None)
        if pages:
            return pages[0]
        raise RuntimeError("Camoufox browser has no page factory")

    def _maybe_warmup(self, page: Any, url: str) -> None:
        warmup = warmup_url_for(url)
        if warmup is None:
            return
        logger.info("camoufox_warmup_origin", extra={"url": warmup})
        try:
            self._goto(page, warmup)
            # Brief pause so JS challenge / cookie minting can finish before product.
            page.wait_for_timeout(min(self._settle_ms, 3_000))
        except Exception:
            logger.warning(
                "camoufox_warmup_failed",
                extra={"url": warmup},
                exc_info=True,
            )

    def _goto(self, page: Any, url: str) -> None:
        page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
        wait_for_load_state = getattr(page, "wait_for_load_state", None)
        if callable(wait_for_load_state):
            try:
                wait_for_load_state(
                    "networkidle", timeout=min(20_000, self._timeout_ms)
                )
            except Exception:
                logger.debug(
                    "camoufox_networkidle_timeout",
                    extra={"url": url},
                    exc_info=True,
                )

    def _wait_for_product_html(
        self,
        page: Any,
        *,
        captured: dict[str, str] | None = None,
    ) -> tuple[str, str, str]:
        html = ""
        final_url = ""
        title = ""
        for attempt in range(max(1, self._max_settle_attempts)):
            if captured and captured.get("body"):
                break
            if attempt > 0:
                page.wait_for_timeout(self._settle_ms)
            html = page.content()
            final_url = str(page.url)
            try:
                title = str(page.title())
            except Exception:
                title = ""
            if is_hard_block_page(html, title=title):
                return html, final_url, title
            if is_shopee_traffic_block(final_url, html):
                return html, final_url, title
            if not is_challenge_page(html, title=title):
                return html, final_url, title
            logger.info(
                "camoufox_waiting_challenge",
                extra={"url": final_url, "attempt": attempt + 1},
            )
        return html, final_url, title

    @classmethod
    def _attach_shopee_get_pc_listener(
        cls,
        page: Any,
        captured: dict[str, str],
        request_url: str,
    ) -> None:
        """Capture the browser's own signed get_pc response (Mode A)."""
        ids = shopee_ids_from_url(request_url)
        wanted_shop = ids[0] if ids else None
        wanted_item = ids[1] if ids else None

        def on_response(response: Any) -> None:
            if captured.get("body"):
                return
            try:
                response_url = str(getattr(response, "url", "") or "")
            except Exception:
                return
            if not is_shopee_get_pc_url(response_url):
                return
            if wanted_shop and wanted_shop not in response_url:
                return
            if wanted_item and wanted_item not in response_url:
                return
            try:
                status = int(getattr(response, "status", 0) or 0)
            except (TypeError, ValueError):
                status = 0
            if status and status >= 400:
                return
            try:
                raw = response.text()
            except Exception:
                logger.debug("shopee_get_pc_body_read_failed", exc_info=True)
                return
            if not isinstance(raw, str) or not raw.strip().startswith("{"):
                return
            if '"error"' in raw[:200] and "90309999" in raw[:400]:
                return
            if not looks_like_shopee_pdp(raw):
                return
            captured["body"] = raw
            captured["response_url"] = response_url

        on_fn = getattr(page, "on", None)
        if not callable(on_fn):
            logger.debug("shopee_get_pc_listener_unavailable")
            return
        on_fn("response", on_response)


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
    camoufox_proxy_url: str | None = None,
    camoufox_user_data_dir: str | None = None,
    camoufox_disable_coop: bool = True,
    camoufox_warmup_origin: bool = True,
) -> HtmlFetcher:
    if camoufox_enabled:
        return CamoufoxHtmlFetcher(
            headless=camoufox_headless,
            humanize=camoufox_humanize,
            timeout_ms=camoufox_timeout_ms,
            settle_ms=camoufox_settle_ms,
            max_settle_attempts=camoufox_max_settle_attempts,
            proxy_url=camoufox_proxy_url,
            user_data_dir=camoufox_user_data_dir,
            disable_coop=camoufox_disable_coop,
            warmup_origin=camoufox_warmup_origin,
        )
    return UrllibHtmlFetcher(user_agent=user_agent, timeout=urllib_timeout)
