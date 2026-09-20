"""Tests for AbsoluteHttpUrl coercion (scheme-less host/path pastes)."""

from __future__ import annotations

from pydantic import ValidationError

from scout_api.core.http_url import AbsoluteHttpUrl, coerce_absolute_http_url
from scout_api.modules.crawler.schemas import CrawlRequest


def test_coerce_prepends_https_for_bare_host_path() -> None:
    raw = (
        "mercadolivre.com.br/placa-de-video-gpu-12gb-dual-asus-geforce-rtx-5070"
        "-oc-editio/p/MLB65069349#polycard_client=recommendations&wid=MLB6801238038"
    )
    assert coerce_absolute_http_url(raw).startswith("https://mercadolivre.com.br/")


def test_coerce_keeps_existing_scheme_and_protocol_relative() -> None:
    assert (
        coerce_absolute_http_url("https://www.kabum.com.br/produto/1")
        == "https://www.kabum.com.br/produto/1"
    )
    assert (
        coerce_absolute_http_url("//www.kabum.com.br/produto/1")
        == "https://www.kabum.com.br/produto/1"
    )


def test_crawl_request_accepts_scheme_less_mercadolivre_url() -> None:
    raw = (
        "mercadolivre.com.br/placa-de-video-gpu-12gb-dual-asus-geforce-rtx-5070"
        "-oc-editio/p/MLB65069349#polycard_client=recommendations_vpp-pdp-v2p-pom"
        "&wid=MLB6801238038&sid=recos"
    )
    req = CrawlRequest.model_validate({"url": raw})
    assert str(req.url).startswith("https://mercadolivre.com.br/")
    assert "MLB65069349" in str(req.url)


def test_absolute_http_url_still_rejects_garbage() -> None:
    try:
        AbsoluteHttpUrl("not a url at all ???")
    except (ValidationError, Exception):
        return
    # Pydantic may wrap differently depending on usage site.
    from pydantic import TypeAdapter

    try:
        TypeAdapter(AbsoluteHttpUrl).validate_python("???")
        raise AssertionError("expected validation failure")
    except ValidationError:
        pass
