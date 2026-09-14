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
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import HTTPCookieProcessor, build_opener
from urllib.request import Request as UrlRequest

from scrapy.http import HtmlResponse, Request

from ..core.exceptions import RequestError, shopee_auth_required_error
from ..core.fetch_metrics import FetchCostMetrics
from ..core.fingerprints import canonicalize_url
from ..core.proxy_policy import proxy_policy_for_url, resolve_store_config

logger = logging.getLogger(__name__)

BrowserFactory = Callable[..., AbstractContextManager[Any]]

SHOPEE_BLOCKED_RESOURCE_TYPES: tuple[str, ...] = ("image", "media", "font")
# Alias: any paid-proxy session runs in minimal-traffic mode.
PROXY_COST_BLOCKED_RESOURCE_TYPES: tuple[str, ...] = SHOPEE_BLOCKED_RESOURCE_TYPES
WarmupPolicy = str  # always | once_per_session | never

# HTTP leg for Amazon only (AmazonHttpFirst). Browser-like UA; not Camoufox spoofing.
_AMAZON_HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


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


def is_akamai_sec_cpt_page(html: str) -> bool:
    """Akamai Bot Manager behavioral / sec-cpt interstitial (Magalu and peers).

    Markers are interstitial-specific (not ordinary Akamai-fronted PDPs). Size
    gate avoids false positives on large pages that happen to mention Akamai.
    """
    text = html or ""
    if len(text) >= 40_000:
        return False
    lower = text.casefold()
    markers = (
        "sec-if-cpt-container",
        "behavioral-content",
        "scf-akamai-logo",
        'id="sec-bc-tile-parent"',
        "sec-bc-text-container",
    )
    if any(marker in lower for marker in markers):
        return True
    # Sensor bootstrap script alone is not exclusive — keep size-gated.
    if len(text) < 8_000 and re.search(
        r"/[_a-z0-9]+/[_a-z0-9]+/[_a-z0-9]+/.+\?v=[0-9a-f-]{8,}",
        lower,
    ):
        if "sec-if-cpt" in lower or "behavioral" in lower:
            return True
    return False


def is_challenge_page(html: str, *, title: str | None = None) -> bool:
    """Detect Cloudflare/Akamai/Amazon interstitials that are not product HTML."""
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
    if is_akamai_sec_cpt_page(html):
        return True
    if "performing security verification" in lower and len(html) < 80_000:
        return True
    if re.search(r"cf-challenge|challenge-platform", lower) and len(html) < 40_000:
        return True
    if is_amazon_robot_check(html, title=title):
        return True
    return False


def is_amazon_robot_check(html: str, *, title: str | None = None) -> bool:
    """Amazon CAPTCHA / robot-check pages must never be parsed as product offers."""
    title_text = (title or "").strip().casefold()
    lower = (html or "")[:20_000].casefold()
    haystack = f"{title_text}\n{lower}"
    markers = (
        "validatecaptcha",
        "/errors/validatecaptcha",
        "opfcaptcha",
        "robot check",
        "type the characters you see",
        "enter the characters you see",
        "sorry, we just need to make sure you're not a robot",
        "clique na caixa para confirmar",
        "não sou um robô",
        "nao sou um robo",
        "to discuss automated access to amazon data",
    )
    if any(marker in haystack for marker in markers):
        return True
    # Short interstitial often lacks #productTitle / ASIN.
    if "amazon" in haystack and "captcha" in haystack and len(html) < 80_000:
        if 'id="producttitle"' not in lower and 'name="asin"' not in lower:
            return True
    return False


def is_auth_wall_page(
    html: str,
    *,
    url: str | None = None,
    title: str | None = None,
) -> bool:
    """Login / soft-auth / session-gate pages that block a public offer scrape."""
    folded_url = (url or "").casefold()
    title_text = (title or "").strip().casefold()
    lower = (html or "")[:40_000].casefold()

    if "ap/signin" in folded_url or "/ap/signin" in lower:
        return True
    if ("amazon." in folded_url or "amazon." in lower[:2_000]) and (
        "sign in" in title_text
        or "sign-in" in title_text
        or "fazer login" in title_text
        or "iniciar sessão" in title_text
        or "iniciar sesion" in title_text
    ):
        if 'id="producttitle"' not in lower and 'name="asin"' not in lower:
            return True

    if "shopee." in folded_url or "shopee." in lower[:2_000]:
        if "/buyer/login" in folded_url:
            return True
        if "login" in folded_url and "next=" in folded_url:
            return True
        if "buyer/login" in lower and "next=" in (folded_url + lower[:4_000]):
            if '"item_id"' not in lower and '"itemid"' not in lower:
                return True

    return False


def needs_interstitial_resolution(
    html: str,
    *,
    url: str | None = None,
    title: str | None = None,
) -> bool:
    """True when challenge/auth wall must be cleared before treating HTML as PDP."""
    if is_hard_block_page(html, title=title):
        return False
    return is_challenge_page(html, title=title) or is_auth_wall_page(
        html, url=url, title=title
    )


def locale_for_url(url: str) -> str | None:
    """Prefer store-local locale so Intl/fingerprint match the target site."""
    hostname = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if hostname == "nissei.com" or hostname.endswith(".nissei.com"):
        return "es-PY"
    if hostname == "magazineluiza.com.br" or hostname.endswith(".magazineluiza.com.br"):
        return "pt-BR"
    if hostname == "shopee.com.br" or hostname.endswith(".shopee.com.br"):
        return "pt-BR"
    if hostname == "amazon.com.br" or hostname.endswith(".amazon.com.br"):
        return "pt-BR"
    if hostname == "amazon.com" or hostname.endswith(".amazon.com"):
        return "en-US"
    return None


def accept_language_for_url(url: str) -> str:
    """HTTP Accept-Language aligned with ``locale_for_url`` (no spoofed geo)."""
    locale = locale_for_url(url)
    if locale == "pt-BR":
        return "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    if locale == "es-PY":
        return "es-PY,es;q=0.9,en;q=0.8"
    if locale == "en-US":
        return "en-US,en;q=0.9"
    return "en-US,en;q=0.9"


def marketplace_referer_for_url(url: str) -> str | None:
    """Same-marketplace Referer for Amazon PDP fetches (session continuity)."""
    hostname = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if hostname == "amazon.com.br" or hostname.endswith(".amazon.com.br"):
        return "https://www.amazon.com.br/"
    if hostname == "amazon.com" or hostname.endswith(".amazon.com"):
        return "https://www.amazon.com/"
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
    if hostname == "magazineluiza.com.br" or hostname.endswith(".magazineluiza.com.br"):
        # Mint Akamai/_abck cookies on the origin before the PDP (ADR 0017).
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


def wrap_shopee_search_json(raw: str) -> str:
    """Embed a captured search_items JSON body for SERP parsing."""
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        "<title>Shopee Search</title></head><body>"
        f'<script type="application/json" data-shopee-search="1">{raw}</script>'
        "</body></html>"
    )


def is_shopee_get_pc_url(url: str) -> bool:
    path = (urlparse(url).path or "").casefold()
    return "/api/v4/pdp/get_pc" in path or path.endswith("/api/v4/pdp/get")


def is_shopee_search_page_url(url: str) -> bool:
    """True for Shopee HTML search pages (not the JSON API itself)."""
    if not is_shopee_url(url):
        return False
    path = (urlparse(url).path or "").casefold().rstrip("/")
    return path == "/search" or path.startswith("/search/")


def is_shopee_search_api_url(url: str) -> bool:
    path = (urlparse(url).path or "").casefold()
    return "/api/v4/search/search_items" in path


def looks_like_shopee_search_payload(raw: str) -> bool:
    sample = (raw or "")[:4_000].casefold()
    if '"error"' in sample[:300] and "90309999" in sample[:500]:
        return False
    return '"items"' in sample or '"item_basic"' in sample or '"itemid"' in sample


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
        opener: Callable[..., Any] | None = None,
        user_agent: str,
        timeout: int = 30,
    ) -> None:
        if opener is None:
            # Persist cookies across fetches on this instance (session reuse).
            jar = CookieJar()
            self._opener = build_opener(HTTPCookieProcessor(jar)).open
        else:
            self._opener = opener
        self._user_agent = user_agent
        self._timeout = timeout

    def fetch(self, url: str) -> HtmlResponse:
        headers = {
            "User-Agent": self._user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": accept_language_for_url(url),
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        referer = marketplace_referer_for_url(url)
        if referer:
            headers["Referer"] = referer
        request = UrlRequest(url, headers=headers)
        try:
            with self._opener(request, timeout=self._timeout) as upstream:
                body = upstream.read()
                status = int(getattr(upstream, "status", 200))
                content_type = upstream.headers.get("Content-Type", "")
                charset = upstream.headers.get_content_charset() or "utf-8"
                final_url = str(getattr(upstream, "geturl", lambda: url)() or url)
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
                if is_challenge_page(text) or is_auth_wall_page(
                    text, url=final_url or url
                ):
                    raise RequestError(
                        "A loja bloqueou a requisição (desafio anti-bot / auth wall)",
                        code="UPSTREAM_BLOCKED",
                        url=final_url or url,
                        upstream_status=403,
                        retryable=True,
                    )
                return HtmlResponse(
                    url=final_url,
                    status=status,
                    headers={"Content-Type": content_type},
                    body=body,
                    encoding=charset,
                    request=Request(final_url),
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
        challenge_resolver: Any | None = None,
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
        self._challenge_resolver = challenge_resolver
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
                shopee_search = is_shopee_search_page_url(url)
                if shopee:
                    if shopee_search:
                        self._attach_shopee_search_listener(page, captured)
                    else:
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
                    page, captured=captured, resume_url=url
                )
                if captured.get("body"):
                    if shopee_search or captured.get("kind") == "search":
                        html = wrap_shopee_search_json(captured["body"])
                        final_url = url
                        title = "Shopee Search"
                        metrics.get_pc_captured = True
                        logger.info(
                            "shopee_search_api_intercepted",
                            extra={"url": captured.get("response_url") or url},
                        )
                    else:
                        html = wrap_shopee_pdp_json(captured["body"])
                        final_url = url
                        title = "Shopee PDP"
                        metrics.get_pc_captured = True
                        logger.info(
                            "shopee_get_pc_intercepted",
                            extra={"url": captured.get("response_url") or url},
                        )
                if is_shopee_traffic_block(final_url or url, html):
                    # Prefer a captured signed search payload over a traffic wall.
                    if not (
                        captured.get("body")
                        and (shopee_search or captured.get("kind") == "search")
                    ):
                        metrics.result = "blocked"
                        self._log_metrics(metrics, request_types, byte_holder["n"], t0)
                        raise shopee_auth_required_error(url=final_url or url)
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
                if needs_interstitial_resolution(
                    html, url=final_url or url, title=title
                ):
                    # ADR 0017 / 0018: attempt CAPTCHA + auth-wall resolution.
                    if self._challenge_resolver is not None:
                        resolved = self._challenge_resolver.try_resolve(
                            page,
                            html=html,
                            title=title,
                            page_url=final_url or url,
                            resume_url=url,
                        )
                        if resolved:
                            html = page.content()
                            final_url = str(page.url)
                            try:
                                title = str(page.title())
                            except Exception:
                                title = title
                            metrics.retry_count = int(metrics.retry_count) + 1
                    if needs_interstitial_resolution(
                        html, url=final_url or url, title=title
                    ):
                        metrics.result = "blocked"
                        self._log_metrics(metrics, request_types, byte_holder["n"], t0)
                        page_url = final_url or url
                        if is_auth_wall_page(html, url=page_url, title=title):
                            if is_shopee_url(page_url):
                                raise shopee_auth_required_error(url=page_url)
                            raise RequestError(
                                "A loja exige login/sessão autenticada "
                                "(falta de login). Configure as credenciais "
                                "da loja no ambiente ou faça o seed da sessão.",
                                code="AUTH_REQUIRED",
                                url=page_url,
                                upstream_status=401,
                                retryable=True,
                            )
                        raise RequestError(
                            "A loja bloqueou a requisição "
                            "(desafio/auth wall após tentativa de resolução)",
                            code="UPSTREAM_BLOCKED",
                            url=page_url,
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
        resume_url: str | None = None,
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
            if not needs_interstitial_resolution(html, url=final_url, title=title):
                return html, final_url, title
            logger.info(
                "camoufox_waiting_challenge",
                extra={"url": final_url, "attempt": attempt + 1},
            )
            # Mid-settle resolution (CAPTCHA / CF / auth wall).
            if self._challenge_resolver is not None and attempt >= 1:
                if self._challenge_resolver.try_resolve(
                    page,
                    html=html,
                    title=title,
                    page_url=final_url,
                    resume_url=resume_url,
                ):
                    html = page.content()
                    final_url = str(page.url)
                    try:
                        title = str(page.title())
                    except Exception:
                        title = title
                    if not needs_interstitial_resolution(
                        html, url=final_url, title=title
                    ):
                        return html, final_url, title
        return html, final_url, title

    @classmethod
    def _attach_shopee_search_listener(
        cls,
        page: Any,
        captured: dict[str, str],
    ) -> None:
        """Capture the browser's own signed ``search_items`` response."""

        def on_response(response: Any) -> None:
            if captured.get("body"):
                return
            try:
                response_url = str(getattr(response, "url", "") or "")
            except Exception:
                return
            if not is_shopee_search_api_url(response_url):
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
                logger.debug("shopee_search_body_read_failed", exc_info=True)
                return
            if not isinstance(raw, str) or not raw.strip().startswith("{"):
                return
            if not looks_like_shopee_search_payload(raw):
                return
            captured["body"] = raw
            captured["response_url"] = response_url
            captured["kind"] = "search"

        on_fn = getattr(page, "on", None)
        if not callable(on_fn):
            logger.debug("shopee_search_listener_unavailable")
            return
        on_fn("response", on_response)

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
            captured["kind"] = "pdp"

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
    captcha_solver_enabled: bool = True,
    captcha_solver_provider: str = "amazoncaptcha",
    captcha_solver_max_attempts: int = 2,
    auth_bypass_enabled: bool = True,
    auth_bypass_max_attempts: int = 2,
    amazon_auth_email: str | None = None,
    amazon_auth_password: str | None = None,
    shopee_auth_email: str | None = None,
    shopee_auth_password: str | None = None,
) -> HtmlFetcher:
    """Build the shared store-aware fetcher (direct + optional proxied Camoufox)."""
    from .challenge_resolution import (
        ChallengeResolver,
        StoreAuthCredentials,
        build_image_captcha_solver,
    )

    http = UrllibHtmlFetcher(user_agent=user_agent, timeout=urllib_timeout)
    if not camoufox_enabled:
        return http

    from .amazon_http_first_fetcher import AmazonHttpFirstHtmlFetcher
    from .store_aware_fetcher import StoreAwareHtmlFetcher

    image_solver = build_image_captcha_solver(
        enabled=captcha_solver_enabled,
        provider=captcha_solver_provider,
    )
    resolve_attempts = max(
        1,
        captcha_solver_max_attempts,
        auth_bypass_max_attempts,
    )
    challenge_resolver = ChallengeResolver(
        image_solver=image_solver,
        max_attempts=resolve_attempts,
        soft_wait_ms=min(8_000, max(1_000, camoufox_settle_ms)),
        enabled=captcha_solver_enabled or auth_bypass_enabled,
        auth_bypass_enabled=auth_bypass_enabled,
        credentials=StoreAuthCredentials(
            amazon_email=amazon_auth_email,
            amazon_password=amazon_auth_password,
            shopee_email=shopee_auth_email,
            shopee_password=shopee_auth_password,
        ),
    )

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
        "challenge_resolver": challenge_resolver,
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
    browser = StoreAwareHtmlFetcher(direct=direct, proxied=proxied, http=http)
    # Amazon HTTP leg only (non-Amazon never hits this fetcher).
    amazon_http = UrllibHtmlFetcher(
        user_agent=_AMAZON_HTTP_USER_AGENT,
        timeout=urllib_timeout,
    )
    return AmazonHttpFirstHtmlFetcher(http=amazon_http, browser=browser)
