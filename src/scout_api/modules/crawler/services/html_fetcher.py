"""HTML fetch strategies for product pages.

Spiders only parse ``HtmlResponse``; fetchers own upstream access and WAF waits.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from scrapy.http import HtmlResponse, Request

from ..core.exceptions import RequestError
from ..core.fetch_metrics import FetchCostMetrics
from ..core.fingerprints import canonicalize_url
from ..core.proxy_policy import proxy_policy_for_url, resolve_store_config

logger = logging.getLogger(__name__)

BrowserFactory = Callable[..., AbstractContextManager[Any]]

SHOPEE_BLOCKED_RESOURCE_TYPES: tuple[str, ...] = ("image", "media", "font")
# Alias: any paid-proxy session runs in minimal-traffic mode.
PROXY_COST_BLOCKED_RESOURCE_TYPES: tuple[str, ...] = SHOPEE_BLOCKED_RESOURCE_TYPES
WarmupPolicy = str  # always | once_per_session | never


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


def _estimate_response_bytes(response: Any) -> int:
    try:
        headers = getattr(response, "headers", None)
        if headers is not None:
            cl = headers.get("content-length")
            if cl is not None:
                return max(0, int(cl))
    except Exception:
        pass
    try:
        body = response.body()
        if body is not None:
            return len(body)
    except Exception:
        pass
    return 0


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
        warmup_policy: WarmupPolicy = "always",
        block_resource_types: Sequence[str] | None = None,
        early_stop_on_shopee_get_pc: bool = True,
        fetch_strategy: str = "camoufox",
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
        self._warmup_policy = warmup_policy
        self._block_resource_types = tuple(block_resource_types or ())
        self._early_stop_on_shopee_get_pc = early_stop_on_shopee_get_pc
        self._fetch_strategy = fetch_strategy
        self._browser_factory = browser_factory
        self._lock = threading.Lock()
        self._warmed_origins: set[str] = set()

    @property
    def proxy_url(self) -> str | None:
        return self._proxy_url

    @property
    def block_resource_types(self) -> tuple[str, ...]:
        return self._block_resource_types

    @property
    def warmed_origins(self) -> frozenset[str]:
        return frozenset(self._warmed_origins)

    def fetch(self, url: str) -> HtmlResponse:
        with self._lock:
            return self._fetch_locked(url)

    def _fetch_locked(self, url: str) -> HtmlResponse:
        store_cfg = resolve_store_config(url)
        metrics = FetchCostMetrics(
            store=store_cfg.key if store_cfg else None,
            canonical_url=canonicalize_url(url),
            proxy_used=bool(self._proxy_url),
            proxy_policy=proxy_policy_for_url(url).value,
            fetch_strategy=self._fetch_strategy,
            blocked_resource_types=self._block_resource_types,
        )
        request_types: Counter[str] = Counter()
        transferred = 0
        t0 = time.perf_counter()
        try:
            with self._open_browser(url=url) as browser:
                page = self._new_page(browser)
                self._maybe_attach_resource_blocking(page, url)
                self._attach_cost_listeners(page, request_types)
                byte_holder = {"n": 0}

                def on_response(response: Any) -> None:
                    byte_holder["n"] += _estimate_response_bytes(response)

                on_fn = getattr(page, "on", None)
                if callable(on_fn):
                    on_fn("response", on_response)

                captured: dict[str, str] = {}
                shopee = is_shopee_url(url)
                if shopee:
                    self._attach_shopee_get_pc_listener(page, captured, url)
                warmup_used = False
                if self._should_warmup(url):
                    warmup_used = self._maybe_warmup(page, url)
                metrics.warmup_used = warmup_used

                if shopee and self._early_stop_on_shopee_get_pc:
                    self._goto_shopee_early_stop(page, url, captured)
                    metrics.early_stop = True
                else:
                    self._goto(page, url)

                html, final_url, title = self._wait_for_product_html(
                    page, captured=captured
                )
                if captured.get("body"):
                    html = wrap_shopee_pdp_json(captured["body"])
                    final_url = url
                    title = "Shopee PDP"
                    metrics.get_pc_captured = True
                    logger.info(
                        "shopee_get_pc_intercepted",
                        extra={"url": captured.get("response_url") or url},
                    )
                if is_shopee_traffic_block(final_url or url, html):
                    metrics.result = "blocked"
                    self._log_metrics(metrics, request_types, byte_holder["n"], t0)
                    raise RequestError(
                        "Shopee bloqueou a requisição "
                        "(verificação de tráfego / anti-bot)",
                        code="UPSTREAM_BLOCKED",
                        url=final_url or url,
                        upstream_status=403,
                        retryable=True,
                    )
                if is_hard_block_page(html, title=title):
                    metrics.result = "blocked"
                    self._log_metrics(metrics, request_types, byte_holder["n"], t0)
                    raise RequestError(
                        "A loja bloqueou o IP de saída (hard-block anti-bot); "
                        "configure um proxy residencial (CAMOUFOX_PROXY_URL)",
                        code="UPSTREAM_BLOCKED",
                        url=final_url or url,
                        upstream_status=403,
                        retryable=False,
                    )
                if is_challenge_page(html, title=title):
                    metrics.result = "blocked"
                    self._log_metrics(metrics, request_types, byte_holder["n"], t0)
                    raise RequestError(
                        "A loja bloqueou a requisição (desafio anti-bot)",
                        code="UPSTREAM_BLOCKED",
                        url=final_url or url,
                        upstream_status=403,
                        retryable=True,
                    )
                body = html.encode("utf-8")
                response = HtmlResponse(
                    url=final_url or url,
                    status=200,
                    headers={"Content-Type": "text/html; charset=utf-8"},
                    body=body,
                    encoding="utf-8",
                    request=Request(url),
                )
                transferred = byte_holder["n"]
                metrics.result = "success"
                self._log_metrics(metrics, request_types, transferred, t0)
                response.meta["fetch_metrics"] = metrics.as_log_dict()
                try:
                    page.close()
                except Exception:
                    logger.debug("camoufox_page_close_failed", exc_info=True)
                return response
        except RequestError:
            raise
        except Exception as exc:
            metrics.result = "error"
            self._log_metrics(metrics, request_types, transferred, t0)
            logger.exception("camoufox_fetch_failed", extra={"url": url})
            raise RequestError(
                "Falha ao renderizar a página com Camoufox",
                code="UPSTREAM_REQUEST_ERROR",
                url=url,
                retryable=True,
            ) from exc

    def _log_metrics(
        self,
        metrics: FetchCostMetrics,
        request_types: Counter[str],
        transferred: int,
        t0: float,
    ) -> None:
        metrics.network_request_count = sum(request_types.values())
        metrics.requests_by_resource_type = dict(request_types)
        metrics.estimated_transferred_bytes = transferred
        metrics.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        payload = metrics.as_log_dict()
        logger.info(
            "fetch_cost_metrics store=%s proxy_used=%s proxy_policy=%s "
            "warmup_used=%s get_pc_captured=%s early_stop=%s "
            "network_request_count=%s estimated_transferred_bytes=%s "
            "duration_ms=%s result=%s requests_by_resource_type=%s",
            payload.get("store"),
            payload.get("proxy_used"),
            payload.get("proxy_policy"),
            payload.get("warmup_used"),
            payload.get("get_pc_captured"),
            payload.get("early_stop"),
            payload.get("network_request_count"),
            payload.get("estimated_transferred_bytes"),
            payload.get("duration_ms"),
            payload.get("result"),
            payload.get("requests_by_resource_type"),
            extra=payload,
        )

    def _attach_cost_listeners(
        self,
        page: Any,
        request_types: Counter[str],
    ) -> None:
        def on_request(request: Any) -> None:
            rtype = str(getattr(request, "resource_type", "unknown") or "unknown")
            request_types[rtype] += 1

        on_fn = getattr(page, "on", None)
        if callable(on_fn):
            on_fn("request", on_request)

    def _maybe_attach_resource_blocking(self, page: Any, url: str) -> None:
        # Proxy cost mode: abort heavy assets on any proxied navigation.
        del url
        if not self._block_resource_types:
            return
        blocked = set(self._block_resource_types)
        route_fn = getattr(page, "route", None)
        if not callable(route_fn):
            logger.debug("camoufox_route_unavailable")
            return

        def _route(route: Any, request: Any) -> None:
            if getattr(request, "resource_type", None) in blocked:
                route.abort()
            else:
                route.continue_()

        route_fn("**/*", _route)

    def _should_warmup(self, url: str) -> bool:
        if not self._warmup_origin:
            return False
        if self._warmup_policy == "never":
            return False
        warm = warmup_url_for(url)
        if warm is None:
            return False
        if self._warmup_policy == "once_per_session":
            origin = (urlparse(warm).netloc or "").lower()
            return bool(origin) and origin not in self._warmed_origins
        return True

    def _mark_warmup(self, url: str) -> None:
        warm = warmup_url_for(url)
        if warm is None:
            return
        origin = (urlparse(warm).netloc or "").lower()
        if origin:
            self._warmed_origins.add(origin)

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

    def _maybe_warmup(self, page: Any, url: str) -> bool:
        warmup = warmup_url_for(url)
        if warmup is None:
            return False
        logger.info("camoufox_warmup_origin", extra={"url": warmup})
        try:
            self._goto(page, warmup)
            # Brief pause so JS challenge / cookie minting can finish before product.
            page.wait_for_timeout(min(self._settle_ms, 3_000))
            self._mark_warmup(url)
            return True
        except Exception:
            logger.warning(
                "camoufox_warmup_failed",
                extra={"url": warmup},
                exc_info=True,
            )
            return False

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

    def _goto_shopee_early_stop(
        self, page: Any, url: str, captured: dict[str, str]
    ) -> None:
        """Navigate to PDP and stop as soon as a valid get_pc payload arrives."""
        page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
        deadline = time.perf_counter() + (self._timeout_ms / 1000.0)
        while not captured.get("body") and time.perf_counter() < deadline:
            if is_shopee_traffic_block(str(getattr(page, "url", "") or ""), ""):
                break
            page.wait_for_timeout(150)
        if captured.get("body"):
            self._mark_warmup(url)

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


def profile_dirs_for_base(base: Path) -> tuple[Path, Path]:
    """Return ``(direct_profile, proxied_profile)`` under the Camoufox profiles root."""
    # Seeded sticky Shopee sessions live in ``default``; direct stores use a sibling.
    if base.name == "default":
        return base.parent / "direct", base
    return Path(f"{base}-direct"), base


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
    shopee_warmup_policy: WarmupPolicy = "once_per_session",
    shopee_resource_blocking_enabled: bool = True,
) -> HtmlFetcher:
    """Build the shared store-aware fetcher (direct + optional proxied Camoufox)."""
    if not camoufox_enabled:
        return UrllibHtmlFetcher(user_agent=user_agent, timeout=urllib_timeout)

    from .store_aware_fetcher import StoreAwareHtmlFetcher

    base_dir = (
        Path(camoufox_user_data_dir)
        if camoufox_user_data_dir
        else default_user_data_dir()
    )
    direct_dir, proxy_dir = profile_dirs_for_base(base_dir)

    common: dict[str, Any] = {
        "headless": camoufox_headless,
        "humanize": camoufox_humanize,
        "timeout_ms": camoufox_timeout_ms,
        "settle_ms": camoufox_settle_ms,
        "max_settle_attempts": camoufox_max_settle_attempts,
        "disable_coop": camoufox_disable_coop,
        "warmup_origin": camoufox_warmup_origin,
    }
    direct = CamoufoxHtmlFetcher(
        **common,
        proxy_url=None,
        user_data_dir=direct_dir,
        warmup_policy="once_per_session",
        early_stop_on_shopee_get_pc=True,
        fetch_strategy="camoufox-direct",
    )
    proxied: CamoufoxHtmlFetcher | None = None
    if camoufox_proxy_url:
        proxied = CamoufoxHtmlFetcher(
            **common,
            proxy_url=camoufox_proxy_url,
            user_data_dir=proxy_dir,
            warmup_policy=shopee_warmup_policy,
            block_resource_types=(
                PROXY_COST_BLOCKED_RESOURCE_TYPES
                if shopee_resource_blocking_enabled
                else ()
            ),
            early_stop_on_shopee_get_pc=True,
            fetch_strategy="camoufox-proxy",
        )
    return StoreAwareHtmlFetcher(direct=direct, proxied=proxied)
