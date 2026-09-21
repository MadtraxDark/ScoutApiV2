"""Unit tests for challenge / CAPTCHA / auth-wall resolution (ADR 0017, 0018)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from scrapy.http import HtmlResponse

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.services.challenge_resolution import (
    AmazonCaptchaLocalSolver,
    ChallengeKind,
    ChallengeResolver,
    RequestErrorAdapter,
    StoreAuthCredentials,
    build_image_captcha_solver,
    classify_challenge,
    extract_amazon_captcha_image_url,
    extract_auth_resume_url,
)
from scout_api.modules.crawler.services.html_fetcher import (
    CamoufoxHtmlFetcher,
    is_auth_wall_page,
)

CHALLENGE_HTML = (
    "<html><head><title>Amazon.com</title></head><body>"
    '<form action="/errors/validateCaptcha">'
    "<h4>Enter the characters you see below</h4>"
    '<img src="https://images-na.ssl-images-amazon.com/captcha/x/Captcha.jpg"/>'
    '<input id="captchacharacters" name="field-keywords" type="text"/>'
    '<button type="submit">Continue shopping</button>'
    "</form></body></html>"
)

PDP_HTML = (
    "<html><head><title>Phone</title></head><body>"
    '<span id="productTitle">Phone</span>'
    '<input id="ASIN" value="B09V9Z1WLN"/>'
    '<div id="ppd"><span class="priceToPay">'
    '<span class="a-offscreen">$10.00</span></span></div>'
    "</body></html>"
)


def test_classify_amazon_and_hard_block() -> None:
    amazon = classify_challenge(CHALLENGE_HTML, title="Amazon.com")
    assert amazon is not None
    assert amazon.kind is ChallengeKind.AMAZON_IMAGE_CAPTCHA
    assert amazon.resolvable is True

    hard = classify_challenge(
        "<html><h1>Sorry, you have been blocked</h1></html>",
        title="Attention Required! | Cloudflare",
    )
    assert hard is not None
    assert hard.kind is ChallengeKind.HARD_BLOCK
    assert hard.resolvable is False

    assert classify_challenge(PDP_HTML, title="Phone") is None

    akamai_html = (
        "<html><body><div id='sec-if-cpt-container'>"
        "<div class='behavioral-content'></div></div></body></html>"
    )
    akamai = classify_challenge(akamai_html, title="")
    assert akamai is not None
    assert akamai.kind is ChallengeKind.AKAMAI_SEC_CPT
    assert akamai.resolvable is True


def test_resolve_akamai_sec_cpt_clears_after_interaction() -> None:
    class FakeMouse:
        def move(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def down(self) -> None:
            return None

        def up(self) -> None:
            return None

    class FakePage:
        def __init__(self) -> None:
            self.calls = 0
            self.mouse = FakeMouse()
            self.viewport_size = {"width": 1280, "height": 720}

        def content(self) -> str:
            self.calls += 1
            if self.calls < 3:
                return (
                    "<html><body><div id='sec-if-cpt-container'>"
                    "<button id='progress-button'>Hold</button>"
                    "</div></body></html>"
                )
            return (
                "<html><body><h1>Produto</h1>"
                "<script id='__NEXT_DATA__'>"
                '{"props":{"pageProps":{"data":{"item":{"id":"1"}}}}}'
                "</script></body></html>"
            )

        def title(self) -> str:
            return "Produto" if self.calls >= 3 else ""

        def url(self) -> str:
            return "https://www.magazineluiza.com.br/p/1"

        def wait_for_timeout(self, _ms: int) -> None:
            return None

        def locator(self, selector: str) -> Any:
            class Loc:
                def __init__(self, page: FakePage, sel: str) -> None:
                    self._page = page
                    self._sel = sel

                @property
                def first(self) -> Loc:
                    return self

                def count(self) -> int:
                    return 1 if "progress-button" in self._sel else 0

                def bounding_box(self) -> dict[str, float]:
                    return {"x": 100, "y": 100, "width": 80, "height": 40}

            return Loc(self, selector)

        def goto(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    page = FakePage()
    resolver = ChallengeResolver(soft_wait_ms=1_000, max_attempts=2)
    assert resolver.try_resolve(
        page,
        html=page.content(),
        title="",
        page_url="https://www.magazineluiza.com.br/p/1",
        resume_url="https://www.magazineluiza.com.br/p/1",
    )


def test_extract_amazon_captcha_image_url() -> None:
    url = extract_amazon_captcha_image_url(CHALLENGE_HTML)
    assert url is not None
    assert "captcha" in url.casefold()


def test_build_image_captcha_solver_defaults_to_amazoncaptcha() -> None:
    solver = build_image_captcha_solver(enabled=True, provider="amazoncaptcha")
    assert isinstance(solver, AmazonCaptchaLocalSolver)
    assert build_image_captcha_solver(enabled=False) is None


def test_amazoncaptcha_local_solver_uses_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    import types
    from io import BytesIO

    captured: dict[str, Any] = {}

    class FakeAmazonCaptcha:
        def __init__(self, img: Any) -> None:
            captured["img"] = img

        def solve(self) -> str:
            return "QX9T"

    fake_mod = types.ModuleType("amazoncaptcha")
    fake_mod.AmazonCaptcha = FakeAmazonCaptcha  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "amazoncaptcha", fake_mod)

    solver = AmazonCaptchaLocalSolver()
    assert solver.solve_image(b"img-bytes") == "QX9T"
    assert isinstance(captured["img"], BytesIO)
    assert captured["img"].getvalue() == b"img-bytes"


def test_amazoncaptcha_local_solver_rejects_unsolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    import types

    class FakeAmazonCaptcha:
        def __init__(self, img: Any) -> None:
            del img

        def solve(self) -> str:
            return "Not solved"

    fake_mod = types.ModuleType("amazoncaptcha")
    fake_mod.AmazonCaptcha = FakeAmazonCaptcha  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "amazoncaptcha", fake_mod)

    with pytest.raises(RequestErrorAdapter):
        AmazonCaptchaLocalSolver().solve_image(b"img-bytes")


def test_camoufox_resolves_amazon_captcha_before_success(tmp_path: Any) -> None:
    class FakeHandle:
        def __init__(self, page: FakePage) -> None:
            self._page = page

        def fill(self, value: str) -> None:
            self._page.filled = value

        def click(self) -> None:
            self._page.submitted = True
            self._page.html = PDP_HTML
            self._page.title_text = "Phone"

    class FakePage:
        url = "https://www.amazon.com/dp/B09V9Z1WLN"

        def __init__(self) -> None:
            self.html = CHALLENGE_HTML
            self.title_text = "Amazon.com"
            self.filled: str | None = None
            self.submitted = False

        def goto(self, url: str, **kwargs: Any) -> None:
            del url, kwargs

        def content(self) -> str:
            return self.html

        def title(self) -> str:
            return self.title_text

        def wait_for_timeout(self, ms: int) -> None:
            del ms

        def query_selector(self, selector: str) -> FakeHandle | None:
            if "captchacharacters" in selector or "field-keywords" in selector:
                return FakeHandle(self)
            if "submit" in selector:
                return FakeHandle(self)
            return None

        def evaluate(self, script: str, arg: str | None = None) -> list[int]:
            del script, arg
            return list(b"img-bytes")

        @property
        def keyboard(self) -> Any:
            page = self

            class K:
                def press(self, key: str) -> None:
                    del key
                    page.submitted = True
                    page.html = PDP_HTML
                    page.title_text = "Phone"

            return K()

        def close(self) -> None:
            return None

    class FakeBrowser:
        def new_page(self) -> FakePage:
            return FakePage()

    @contextmanager
    def fake_factory(**kwargs: Any) -> Iterator[FakeBrowser]:
        del kwargs
        yield FakeBrowser()

    class FakeSolver:
        def solve_image(self, image_bytes: bytes) -> str:
            assert image_bytes == b"img-bytes"
            return "QX9T"

    resolver = ChallengeResolver(
        image_solver=FakeSolver(),
        max_attempts=1,
        soft_wait_ms=1,
        enabled=True,
    )
    fetcher = CamoufoxHtmlFetcher(
        browser_factory=fake_factory,
        settle_ms=0,
        max_settle_attempts=1,
        user_data_dir=tmp_path / "profile",
        warmup_origin=False,
        challenge_resolver=resolver,
    )
    response = fetcher.fetch("https://www.amazon.com/dp/B09V9Z1WLN")
    assert isinstance(response, HtmlResponse)
    assert "productTitle" in response.text
    assert response.meta["fetch_metrics"]["result"] == "success"


def test_camoufox_still_blocks_when_resolver_fails(tmp_path: Any) -> None:
    class FakePage:
        url = "https://www.amazon.com/dp/B09V9Z1WLN"

        def goto(self, url: str, **kwargs: Any) -> None:
            del url, kwargs

        def content(self) -> str:
            return CHALLENGE_HTML

        def title(self) -> str:
            return "Amazon.com"

        def wait_for_timeout(self, ms: int) -> None:
            del ms

        def close(self) -> None:
            return None

    class FakeBrowser:
        def new_page(self) -> FakePage:
            return FakePage()

    @contextmanager
    def fake_factory(**kwargs: Any) -> Iterator[FakeBrowser]:
        del kwargs
        yield FakeBrowser()

    class FailingSolver:
        def solve_image(self, image_bytes: bytes) -> str:
            del image_bytes
            raise RuntimeError("solver down")

    fetcher = CamoufoxHtmlFetcher(
        browser_factory=fake_factory,
        settle_ms=0,
        max_settle_attempts=1,
        user_data_dir=tmp_path / "profile",
        warmup_origin=False,
        challenge_resolver=ChallengeResolver(
            image_solver=FailingSolver(),
            max_attempts=1,
            soft_wait_ms=1,
            enabled=True,
        ),
    )
    with pytest.raises(RequestError) as exc:
        fetcher.fetch("https://www.amazon.com/dp/B09V9Z1WLN")
    assert exc.value.code == "UPSTREAM_BLOCKED"
    assert (
        "resolução" in exc.value.args[0].casefold()
        or "desafio" in exc.value.args[0].casefold()
        or "auth" in exc.value.args[0].casefold()
    )


AUTH_WALL_HTML = (
    "<html><head><title>Amazon Sign-In</title></head><body>"
    '<form name="signIn">'
    '<input id="ap_email" name="email" type="email"/>'
    '<input id="ap_password" name="password" type="password"/>'
    '<input id="signInSubmit" type="submit" value="Sign in"/>'
    "</form></body></html>"
)

SHOPEE_LOGIN_URL = (
    "https://shopee.com.br/buyer/login?next=https%3A%2F%2Fshopee.com.br%2Fitem-i.1.2"
)


def test_is_auth_wall_and_classify() -> None:
    assert is_auth_wall_page(
        AUTH_WALL_HTML,
        url="https://www.amazon.com/ap/signin?openid.return_to=https://www.amazon.com/dp/B09V9Z1WLN",
        title="Amazon Sign-In",
    )
    assert is_auth_wall_page(
        "<html><body>login</body></html>",
        url=SHOPEE_LOGIN_URL,
        title="Shopee",
    )
    assert not is_auth_wall_page(PDP_HTML, url="https://www.amazon.com/dp/B09V9Z1WLN")

    assessment = classify_challenge(
        AUTH_WALL_HTML,
        title="Amazon Sign-In",
        url="https://www.amazon.com/ap/signin",
    )
    assert assessment is not None
    assert assessment.kind is ChallengeKind.AUTH_WALL
    assert assessment.resolvable is True


def test_extract_auth_resume_url() -> None:
    resume = extract_auth_resume_url(
        "https://shopee.com.br/buyer/login?next=https%3A%2F%2Fshopee.com.br%2Fx",
        fallback="https://fallback.example/",
    )
    assert resume == "https://shopee.com.br/x"
    assert (
        extract_auth_resume_url("https://example.com/login", fallback="https://a/")
        == "https://a/"
    )


def test_camoufox_resolves_amazon_auth_wall_with_credentials(tmp_path: Any) -> None:
    class FakeHandle:
        def __init__(self, page: FakePage, kind: str) -> None:
            self._page = page
            self._kind = kind

        def fill(self, value: str) -> None:
            if self._kind == "email":
                self._page.email = value
            elif self._kind == "password":
                self._page.password = value

        def click(self) -> None:
            if self._kind == "submit" and self._page.email and self._page.password:
                self._page.logged_in = True

    class FakePage:
        def __init__(self) -> None:
            self.html = AUTH_WALL_HTML
            self.title_text = "Amazon Sign-In"
            self.url = (
                "https://www.amazon.com/ap/signin?"
                "openid.return_to=https%3A%2F%2Fwww.amazon.com%2Fdp%2FB09V9Z1WLN"
            )
            self.email: str | None = None
            self.password: str | None = None
            self.logged_in = False

        def goto(self, url: str, **kwargs: Any) -> None:
            del kwargs
            if self.logged_in and "/dp/" in url:
                self.html = PDP_HTML
                self.title_text = "Phone"
                self.url = url
                return
            if "/dp/" in url and not self.logged_in:
                self.html = AUTH_WALL_HTML
                self.title_text = "Amazon Sign-In"
                self.url = (
                    "https://www.amazon.com/ap/signin?"
                    "openid.return_to=https%3A%2F%2Fwww.amazon.com%2Fdp%2FB09V9Z1WLN"
                )
                return
            self.url = url

        def content(self) -> str:
            return self.html

        def title(self) -> str:
            return self.title_text

        def wait_for_timeout(self, ms: int) -> None:
            del ms

        def query_selector(self, selector: str) -> FakeHandle | None:
            if "ap_email" in selector or "email" in selector:
                return FakeHandle(self, "email")
            if "ap_password" in selector or "password" in selector:
                return FakeHandle(self, "password")
            if "signInSubmit" in selector or "submit" in selector:
                return FakeHandle(self, "submit")
            return None

        def close(self) -> None:
            return None

    class FakeBrowser:
        def new_page(self) -> FakePage:
            return FakePage()

    @contextmanager
    def fake_factory(**kwargs: Any) -> Iterator[FakeBrowser]:
        del kwargs
        yield FakeBrowser()

    resolver = ChallengeResolver(
        image_solver=None,
        max_attempts=1,
        soft_wait_ms=1,
        enabled=True,
        auth_bypass_enabled=True,
        credentials=StoreAuthCredentials(
            amazon_email="ops@example.com",
            amazon_password="secret",
        ),
    )
    fetcher = CamoufoxHtmlFetcher(
        browser_factory=fake_factory,
        settle_ms=0,
        max_settle_attempts=1,
        user_data_dir=tmp_path / "profile-auth",
        warmup_origin=False,
        challenge_resolver=resolver,
    )
    response = fetcher.fetch("https://www.amazon.com/dp/B09V9Z1WLN")
    assert isinstance(response, HtmlResponse)
    assert "productTitle" in response.text
    assert response.meta["fetch_metrics"]["result"] == "success"


def test_camoufox_blocks_when_auth_wall_unresolved(tmp_path: Any) -> None:
    class FakePage:
        url = "https://www.amazon.com/ap/signin"

        def goto(self, url: str, **kwargs: Any) -> None:
            del url, kwargs

        def content(self) -> str:
            return AUTH_WALL_HTML

        def title(self) -> str:
            return "Amazon Sign-In"

        def wait_for_timeout(self, ms: int) -> None:
            del ms

        def query_selector(self, selector: str) -> None:
            del selector
            return None

        def close(self) -> None:
            return None

    class FakeBrowser:
        def new_page(self) -> FakePage:
            return FakePage()

    @contextmanager
    def fake_factory(**kwargs: Any) -> Iterator[FakeBrowser]:
        del kwargs
        yield FakeBrowser()

    fetcher = CamoufoxHtmlFetcher(
        browser_factory=fake_factory,
        settle_ms=0,
        max_settle_attempts=1,
        user_data_dir=tmp_path / "profile-auth-fail",
        warmup_origin=False,
        challenge_resolver=ChallengeResolver(
            max_attempts=1,
            soft_wait_ms=1,
            enabled=True,
            auth_bypass_enabled=True,
            credentials=None,
        ),
    )
    with pytest.raises(RequestError) as exc:
        fetcher.fetch("https://www.amazon.com/dp/B09V9Z1WLN")
    assert exc.value.code == "AUTH_REQUIRED"
    assert "falta de login" in str(exc.value).casefold()


def test_camoufox_blocks_shopee_traffic_as_auth_required(tmp_path: Any) -> None:
    class FakePage:
        url = "https://shopee.com.br/verify/traffic?anti_bot_tracking_id=x"

        def goto(self, url: str, **kwargs: Any) -> None:
            del kwargs
            self.url = "https://shopee.com.br/verify/traffic?anti_bot_tracking_id=x"

        def content(self) -> str:
            return "<html><title>verify</title><body>verify/traffic</body></html>"

        def title(self) -> str:
            return "verify"

        def wait_for_timeout(self, ms: int) -> None:
            del ms

        def on(self, event: str, handler: Any) -> None:
            del event, handler

        def close(self) -> None:
            return None

    class FakeBrowser:
        def new_page(self) -> FakePage:
            return FakePage()

    @contextmanager
    def fake_factory(**kwargs: Any) -> Iterator[FakeBrowser]:
        del kwargs
        yield FakeBrowser()

    fetcher = CamoufoxHtmlFetcher(
        browser_factory=fake_factory,
        settle_ms=0,
        max_settle_attempts=1,
        user_data_dir=tmp_path / "profile-shopee-auth",
        warmup_origin=False,
    )
    with pytest.raises(RequestError) as exc:
        fetcher.fetch("https://shopee.com.br/product/1/2")
    assert exc.value.code == "AUTH_REQUIRED"
    assert "falta de login" in str(exc.value).casefold()
    assert "SHOPEE_AUTH_EMAIL" in str(exc.value)


def test_classify_prefers_ml_snoopy_over_account_verification() -> None:
    html = (
        "<html><body>"
        "<button id='continue-button' disabled>Continuar</button>"
        "<script src='https://http2.mlstatic.com/frontend-assets/"
        "snoopy-generation-web/latest/snoopy-script.js'></script>"
        "<p>account-verification</p>"
        "</body></html>"
    )
    assessment = classify_challenge(
        html,
        title="Mercado Livre",
        url=(
            "https://www.mercadolivre.com.br/gz/account-verification"
            "?go=https%3A%2F%2Flista.mercadolivre.com.br%2Frtx"
        ),
    )
    assert assessment is not None
    assert assessment.kind is ChallengeKind.MERCADOLIVRE_SNOOPY


def test_ml_auth_bypass_without_credentials() -> None:
    """account-verification clears via warm+resume — no MERCADOLIVRE_AUTH_*."""

    class FakePage:
        def __init__(self) -> None:
            self.url = (
                "https://www.mercadolivre.com.br/gz/account-verification"
                "?go=https%3A%2F%2Flista.mercadolivre.com.br%2Frtx-5060"
            )
            self._mode = "wall"

        def goto(self, url: str, **kwargs: Any) -> None:
            del kwargs
            self.url = url
            if "lista.mercadolivre" in url:
                self._mode = "serp"
            elif "www.mercadolivre.com.br" in url and "/gz/" not in url:
                self._mode = "home"
            else:
                self._mode = "wall"

        def content(self) -> str:
            if self._mode == "serp":
                return (
                    "<html><body class='ui-search-layout'>"
                    "<a class='poly-component__title' href='/p/MLB1'>GPU</a>"
                    "</body></html>"
                )
            if self._mode == "home":
                return "<html><body>Mercado Livre</body></html>"
            return (
                "<html><body>Olá! Para continuar, acesse sua conta"
                "<p>account-verification</p></body></html>"
            )

        def title(self) -> str:
            return "Mercado Livre"

        def wait_for_timeout(self, ms: int) -> None:
            del ms

        def wait_for_function(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def query_selector(self, selector: str) -> None:
            del selector
            return None

    page = FakePage()
    resolver = ChallengeResolver(
        max_attempts=1,
        soft_wait_ms=1,
        enabled=True,
        auth_bypass_enabled=True,
        credentials=None,
    )
    ok = resolver._bypass_mercadolivre_auth_wall(
        page,
        page_url=page.url,
        resume_url="https://lista.mercadolivre.com.br/rtx-5060",
    )
    assert ok is True
    assert "lista.mercadolivre" in page.url
    assert "ui-search-layout" in page.content()
