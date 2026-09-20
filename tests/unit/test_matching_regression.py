"""Regression suite for precision-first product matching."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from scout_api.modules.crawler.models.product import ProductPriceItem
from scout_api.modules.matching.engine import MatchingEngine
from scout_api.modules.matching.identity import (
    ProductIdentity,
    build_search_queries,
    identity_from_price_item,
    normalize_gtin,
    normalize_title,
    token_set_ratio,
)


def _identity(**kwargs: object) -> ProductIdentity:
    defaults: dict[str, object] = {
        "gtin": None,
        "brand": None,
        "model": None,
        "title": "Produto",
        "title_normalized": "produto",
        "variant_attrs": {},
        "store": None,
        "product_id": None,
        "price": Decimal("100.00"),
        "currency": "BRL",
        "mpn": None,
        "mpn_display": None,
    }
    defaults.update(kwargs)
    if "title_normalized" not in kwargs and isinstance(defaults["title"], str):
        defaults["title_normalized"] = normalize_title(defaults["title"])
    return ProductIdentity(**defaults)  # type: ignore[arg-type]


def _item(**overrides: object) -> ProductPriceItem:
    base: dict[str, object] = {
        "store": "kabum",
        "country": "BR",
        "product_id": "1",
        "url": "https://www.kabum.com.br/produto/1",
        "canonical_url": "https://www.kabum.com.br/produto/1",
        "title": "Produto",
        "currency": "BRL",
        "price": Decimal("100.00"),
        "scraped_at": datetime(2026, 9, 19, tzinfo=UTC),
    }
    base.update(overrides)
    return ProductPriceItem.model_validate(base)


def test_same_product_different_title_language_matches() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="apple",
            model="iphone15",
            title="Apple iPhone 15 128GB Blue",
            variant_attrs={"storage": "128gb", "color": "blue"},
        ),
        _identity(
            brand="apple",
            model="iphone15",
            title="Celular Apple iPhone 15 Azul 128 GB",
            variant_attrs={"storage": "128gb", "color": "azul"},
        ),
    )
    assert score.decision == "auto_match"
    assert (
        token_set_ratio(
            "Apple iPhone 15 128GB Blue",
            "Celular Apple iPhone 15 Azul 128 GB",
        )
        >= 0.7
    )


def test_different_storage_rejects() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="apple",
            model="iphone15",
            title="Apple iPhone 15 128GB",
            variant_attrs={"storage": "128gb"},
        ),
        _identity(
            brand="apple",
            model="iphone15",
            title="Apple iPhone 15 256GB",
            variant_attrs={"storage": "256gb"},
        ),
    )
    assert score.decision == "reject"
    assert any(
        r.code in {"variant_mismatch", "critical_conflict"} for r in score.reasons
    )


def test_gpu_ti_suffix_rejects() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="nvidia",
            model="rtx5060",
            title="Placa de Video RTX 5060 8GB",
        ),
        _identity(
            brand="nvidia",
            model="rtx5060ti",
            title="Placa de Video RTX 5060 Ti 16GB",
        ),
    )
    assert score.decision == "reject"
    assert any(r.code == "critical_conflict" for r in score.reasons)


def test_title_noise_still_matches_with_brand_model() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="kingston",
            model="hx432c16fb3",
            title="Kingston HyperX Fury DDR4 8GB",
            mpn="hx432c16fb3",
        ),
        _identity(
            brand="kingston",
            model="hx432c16fb3",
            title="OFERTA Memoria Kingston HyperX Fury 8GB Frete Gratis Oficial",
            mpn="hx432c16fb3",
        ),
    )
    assert score.decision == "auto_match"


def test_missing_structured_model_uses_title_fallback() -> None:
    ref = identity_from_price_item(
        _item(
            title="SSD Samsung 990 EVO Plus 1TB M.2 NVMe - MZ-V9S1T0B/AM",
            brand="Samsung",
            model="MZ-V9S1T0B/AM",
            variant="color: Preto; storage: 1 TB",
        )
    )
    cand = identity_from_price_item(
        _item(
            store="amazon_br",
            product_id="B0DHLFWBQ1",
            title=("Samsung SSD 990 EVO Plus 1TB, PCIe Gen 4x4, MZ-V9S1T0B/AM Preto"),
            brand="Samsung",
            model=None,
            url="https://www.amazon.com.br/dp/B0DHLFWBQ1",
            canonical_url="https://www.amazon.com.br/dp/B0DHLFWBQ1",
        )
    )
    assert ref.model == "990evoplus"
    assert cand.model == "990evoplus"
    assert ref.mpn == cand.mpn == "mzv9s1t0bam"
    score = MatchingEngine().score(ref, cand)
    assert score.decision == "auto_match"
    assert any(r.code in {"mpn_exact", "brand_model_exact"} for r in score.reasons)


def test_gtin_exact_high_confidence() -> None:
    gtin = normalize_gtin("7891991010863")
    assert gtin is not None
    score = MatchingEngine().score(
        _identity(gtin=gtin, brand="nestle", title="Chocolate A"),
        _identity(gtin=gtin, brand="nestle", title="Chocolate B com ruido"),
    )
    assert score.decision == "auto_match"
    assert score.confidence >= Decimal("0.99")


def test_ambiguous_title_only_does_not_auto_match() -> None:
    score = MatchingEngine().score(
        _identity(title="Memoria RAM 8GB DDR4 Desktop"),
        _identity(title="Memoria RAM 8GB DDR4 Notebook"),
    )
    assert score.decision != "auto_match"


def test_ssd_series_mismatch_870_vs_990_rejects() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="samsung",
            model="990evoplus",
            title="SSD Samsung 990 EVO Plus 1TB MZ-V9S1T0B/AM",
            mpn="mzv9s1t0bam",
            variant_attrs={"storage": "1tb"},
        ),
        _identity(
            brand="samsung",
            model="870evo",
            title="Samsung 870 EVO 1TB Internal SSD SATA",
            variant_attrs={"storage": "1tb"},
        ),
    )
    assert score.decision == "reject"
    assert any(r.code == "critical_conflict" for r in score.reasons)


def test_mpn_query_precedes_title_tokens() -> None:
    identity = identity_from_price_item(
        _item(
            title="SSD Samsung 990 EVO Plus 1TB - MZ-V9S1T0B/AM",
            brand="Samsung",
            model="990 Evo Plus",
            variant="storage: 1 TB",
        )
    )
    queries = build_search_queries(identity)
    assert identity.mpn == "mzv9s1t0bam"
    assert identity.mpn_display == "MZ-V9S1T0B/AM"
    assert queries[0] == "MZ-V9S1T0B/AM"
    assert any(q == "samsung 990 evo plus 1tb" for q in queries)
    assert any("mzv9s1t0bam" in q for q in queries)


def test_rank_candidates_prefers_mpn_title_hit() -> None:
    from scout_api.modules.crawler.models.search import SearchCandidate
    from scout_api.modules.matching.identity import rank_candidates_for_query

    ranked = rank_candidates_for_query(
        [
            SearchCandidate(
                url="https://www.amazon.com.br/dp/B0WRONG001",
                title="SSD Samsung 990 PRO 1TB",
                product_id="B0WRONG001",
            ),
            SearchCandidate(
                url="https://www.amazon.com.br/dp/B0DHLFWBQ1",
                title="Samsung SSD 990 EVO Plus 1TB MZ-V9S1T0B/AM",
                product_id="B0DHLFWBQ1",
            ),
        ],
        "MZ-V9S1T0B/AM",
    )
    assert ranked[0].product_id == "B0DHLFWBQ1"


def test_rank_candidates_ignores_amazon_keywords_querystring() -> None:
    """SERP URLs embed keywords=… — must not flatten color ranking."""
    from scout_api.modules.crawler.models.search import SearchCandidate
    from scout_api.modules.matching.identity import rank_candidates_for_query

    ranked = rank_candidates_for_query(
        [
            SearchCandidate(
                url=(
                    "https://www.amazon.com.br/dp/B0TEAL?"
                    "keywords=apple+iphone+16+128gb+preto"
                ),
                title="Apple iPhone 16 (128 GB) – Verde-acinzentado",
                product_id="B0TEAL",
            ),
            SearchCandidate(
                url=(
                    "https://www.amazon.com.br/dp/B0DJFTJ6LX?"
                    "keywords=apple+iphone+16+128gb+preto"
                ),
                title="Apple iPhone 16 (128 GB) – Preto",
                product_id="B0DJFTJ6LX",
            ),
        ],
        "apple iphone 16 128gb preto",
    )
    assert ranked[0].product_id == "B0DJFTJ6LX"


def test_iphone_pro_suffix_rejects() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="apple",
            model="iphone15",
            title="Apple iPhone 15 128GB",
            variant_attrs={"storage": "128gb"},
        ),
        _identity(
            brand="apple",
            model="iphone15pro",
            title="Apple iPhone 15 Pro 128GB",
            variant_attrs={"storage": "128gb"},
        ),
    )
    assert score.decision == "reject"


def test_ddr4_vs_ddr5_rejects() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="kingston",
            model="fury",
            title="Kingston Fury 16GB DDR4 3200",
        ),
        _identity(
            brand="kingston",
            model="fury",
            title="Kingston Fury 16GB DDR5 5600",
        ),
    )
    assert score.decision == "reject"
    assert any(r.code == "critical_conflict" for r in score.reasons)


def test_normalize_title_compacts_capacity_and_mpn() -> None:
    assert "128gb" in normalize_title("iPhone 15 128 GB Blue").split()
    assert "128gb" in normalize_title("iPhone 15 128GB Blue").split()
    assert "mzv9s1t0bam" in normalize_title("SSD Samsung MZ-V9S1T0B/AM 1TB").split()


def test_iphone16_preto_matches_black_cross_locale() -> None:
    ref = identity_from_price_item(
        _item(
            store="magazineluiza",
            product_id="238803400",
            title='Apple iPhone 16 128GB Preto 6,1" 48MP iOS 5G',
            brand="Apple",
            model="iPhone 16",
            variant="Preto",
        )
    )
    cand = identity_from_price_item(
        _item(
            store="amazon_br",
            product_id="B0DJFTJ6LX",
            title="Apple iPhone 16 (128 GB) – Black",
            brand="Apple",
            model="iPhone 16",
            url="https://www.amazon.com.br/dp/B0DJFTJ6LX",
            canonical_url="https://www.amazon.com.br/dp/B0DJFTJ6LX",
            variant="tamanho: 128 GB; cor: Black",
        )
    )
    assert ref.variant_attrs.get("color") == "preto"
    assert cand.variant_attrs.get("color") == "black"
    assert cand.variant_attrs.get("storage") == "128gb"
    score = MatchingEngine().score(ref, cand)
    assert score.decision == "auto_match"


def test_iphone16_rejects_different_color_cor_alias() -> None:
    """Amazon BR publishes ``cor`` / ``tamanho`` — must not drop the color gate."""
    ref = identity_from_price_item(
        _item(
            title="Apple iPhone 16 128GB Preto",
            brand="Apple",
            model="iPhone 16",
            variant="Preto",
        )
    )
    cand = identity_from_price_item(
        _item(
            store="amazon_br",
            product_id="B0DJFSTQHX",
            title="Apple iPhone 16 (128 GB) – Verde-acinzentado",
            brand="Apple",
            model="iPhone 16",
            url="https://www.amazon.com.br/dp/B0DJFSTQHX",
            canonical_url="https://www.amazon.com.br/dp/B0DJFSTQHX",
            variant="tamanho: 128 GB; cor: Verde-Acizentado",
        )
    )
    assert cand.variant_attrs.get("color") is not None
    score = MatchingEngine().score(ref, cand)
    assert score.decision == "reject"
    assert any(r.code == "variant_mismatch" for r in score.reasons)


def test_iphone16_rejects_pro_and_storage_and_16e() -> None:
    ref = identity_from_price_item(
        _item(
            title="Apple iPhone 16 128GB Preto",
            brand="Apple",
            model="iPhone 16",
            variant="Preto",
        )
    )
    engine = MatchingEngine()
    pro = identity_from_price_item(
        _item(
            title="Apple iPhone 16 Pro 128GB Preto",
            brand="Apple",
            model="iPhone 16 Pro",
            variant="Preto",
            product_id="2",
        )
    )
    assert engine.score(ref, pro).decision == "reject"

    gb256 = identity_from_price_item(
        _item(
            title="Apple iPhone 16 256GB Preto",
            brand="Apple",
            model="iPhone 16",
            variant="Preto",
            product_id="3",
            metadata={"storage": "256gb"},
        )
    )
    assert engine.score(ref, gb256).decision == "reject"

    iphone_e = identity_from_price_item(
        _item(
            title="Apple iPhone 16e 128GB Black",
            brand="Apple",
            model="iPhone 16e",
            variant="Black",
            product_id="4",
        )
    )
    assert engine.score(ref, iphone_e).decision == "reject"


def test_iphone16_title_noise_still_matches() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                title='Apple iPhone 16 128GB Preto 5G Tela 6.1"',
                brand="Apple",
                model="iPhone 16",
                variant="Preto",
            )
        ),
        identity_from_price_item(
            _item(
                store="bestbuy",
                product_id="6507508",
                title="iPhone 16 Apple Black 128 GB Unlocked",
                brand="Apple",
                model="iPhone 16",
                url="https://www.bestbuy.com/site/6507508.p",
                canonical_url="https://www.bestbuy.com/site/6507508.p",
                variant="color: Black; storage: 128 GB",
            )
        ),
    )
    assert score.decision == "auto_match"


def test_iphone16_search_queries_include_color_synonyms() -> None:
    identity = identity_from_price_item(
        _item(
            title="Apple iPhone 16 128GB Preto",
            brand="Apple",
            model="iPhone 16",
            variant="Preto",
        )
    )
    queries = build_search_queries(identity)
    assert any("preto" in q for q in queries)
    assert any("black" in q for q in queries)
    assert any(q == "iphone 16 128gb" for q in queries)


def test_renewed_listing_rejects_against_new_reference() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                title="Apple iPhone 16 128GB Black",
                brand="Apple",
                model="iPhone 16",
                variant="Black",
            )
        ),
        identity_from_price_item(
            _item(
                store="amazon_us",
                product_id="B0RENEWED",
                title="Apple iPhone 16, 128GB, Black - Unlocked (Renewed)",
                brand="Apple",
                model="iPhone 16",
                url="https://www.amazon.com/dp/B0RENEWED",
                canonical_url="https://www.amazon.com/dp/B0RENEWED",
                variant="color: Black; storage: 128 GB",
            )
        ),
    )
    assert score.decision == "reject"
    assert any(r.code == "condition_reject" for r in score.reasons)


def test_iphone_bundle_with_watch_rejects() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                title="Apple iPhone 16 128GB Preto",
                brand="Apple",
                model="iPhone 16",
                variant="Preto",
            )
        ),
        identity_from_price_item(
            _item(
                store="magazineluiza",
                product_id="239229600",
                title=(
                    "Smartphone Apple iPhone 16 128GB Preto 5G "
                    "Smartwatch Apple Watch SE 3 40mm"
                ),
                brand="Apple",
                model="iPhone 16",
                url="https://www.magazineluiza.com.br/p/239229600/",
                canonical_url="https://www.magazineluiza.com.br/p/239229600/",
                variant="Preto",
            )
        ),
    )
    assert score.decision == "reject"
    assert any(r.code == "bundle_reject" for r in score.reasons)


def test_missing_controller_count_is_not_a_conflict() -> None:
    """Unknown controller qty must not reject an otherwise matching console."""
    score = MatchingEngine().score(
        _identity(
            brand="sony",
            model="playstation5digital",
            title="Console Sony PlayStation 5 CFI-2115B Digital 825GB 8K",
            variant_attrs={"storage": "825gb", "color": "branco"},
            mpn="cfi2115b",
        ),
        _identity(
            brand="sony",
            model="playstation5digital",
            title="PlayStation 5 Edição Digital 825GB 1 Controle Branco Sony",
            variant_attrs={"storage": "825gb", "color": "branco"},
        ),
    )
    assert score.decision == "auto_match"
    assert not any("controller" in (r.detail or "") for r in score.reasons)


def test_explicit_controller_count_conflict_rejects() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="sony",
            model="playstation5digital",
            title="PlayStation 5 Digital 825GB 1 Controle Branco",
            variant_attrs={"storage": "825gb"},
        ),
        _identity(
            brand="sony",
            model="playstation5digital",
            title="PlayStation 5 Digital 825GB 2 Controles Branco",
            variant_attrs={"storage": "825gb"},
        ),
    )
    assert score.decision == "reject"
    assert any(
        r.code == "critical_conflict" and "controller_count" in (r.detail or "")
        for r in score.reasons
    )


def test_digital_vs_disc_edition_rejects() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="sony",
            model="playstation5digital",
            title="Console Sony PlayStation 5 CFI-2115B Digital 825GB 8K",
            variant_attrs={"storage": "825gb"},
            gtin="0711719021483",
        ),
        _identity(
            brand="sony",
            model="playstation5discversion",
            title=(
                "Sony PlayStation 5 PS5 Disc Version Gaming Console, "
                "Ultra-High Speed 825GB SSD, Bluetooth 5.1, 120Hz 8K Output"
            ),
            variant_attrs={"storage": "825gb"},
        ),
    )
    assert score.decision == "reject"
    assert any(
        r.code == "critical_conflict" and "console_edition" in (r.detail or "")
        for r in score.reasons
    )


def test_storage_825_vs_1tb_rejects() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="sony",
            model="playstation5digital",
            title="PlayStation 5 Digital Edition 825GB",
            variant_attrs={"storage": "825gb"},
        ),
        _identity(
            brand="sony",
            model="playstation5digital",
            title="PlayStation 5 Digital Edition 1TB",
            variant_attrs={"storage": "1tb"},
        ),
    )
    assert score.decision == "reject"
    assert any(
        r.code in {"critical_conflict", "variant_mismatch"}
        and "storage" in (r.detail or "")
        for r in score.reasons
    )


def test_console_plus_fortnite_bundle_rejects_against_bare() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="sony",
            model="playstation5digital",
            title="Console Sony PlayStation 5 CFI-2115B Digital 825GB 8K",
            variant_attrs={"storage": "825gb"},
        ),
        _identity(
            brand="sony",
            model="playstation5digital",
            title=("CONSOLE SONY PLAYSTATION 5 CFI-2115B DIGITAL 825GB 8K + FORTNITE"),
            variant_attrs={"storage": "825gb"},
        ),
    )
    assert score.decision == "reject"
    assert any(r.code == "bundle_reject" for r in score.reasons)


def test_sparse_console_title_still_matches_marketing_title() -> None:
    """Shopping China-style sparse title vs KaBuM marketing must auto_match."""
    score = MatchingEngine().score(
        _identity(
            brand="sony",
            model="playstation5slimdigital",
            title=(
                "Console Sony PlayStation 5 Edição Digital Slim, SSD 825GB, "
                "Controle DualSense, Astro's Playroom, Branco - CFI 2114B"
            ),
            variant_attrs={"storage": "825gb", "color": "branco"},
            mpn="cfi2114b",
        ),
        _identity(
            brand="sony",
            model="playstation5digital",
            title="Console Sony Playstation 5 Cfi 2115 B Digital 825 Gb 8 K",
            variant_attrs={"storage": "825gb", "color": "branco"},
            mpn="cfi2115b",
            gtin="0711719021483",
        ),
    )
    assert score.decision == "auto_match"
    assert any(r.code == "brand_model_exact" for r in score.reasons)


def test_resolve_model_enriches_generic_playstation_from_title() -> None:
    from scout_api.modules.matching.identity import resolve_model

    assert (
        resolve_model(
            "PlayStation 5",
            "Console Sony PlayStation 5 Edição Digital Slim 825GB Branco",
        )
        == "playstation5slimdigital"
    )


def test_ps5_search_queries_omit_slim_and_hyphenate_cfi() -> None:
    """Shopping China empties on brand+slim+storage; hyphenated CFI ranks."""
    from scout_api.modules.matching.identity import (
        ProductIdentity,
        build_search_queries,
        extract_mpn_forms,
    )

    _norm, display = extract_mpn_forms(
        "PlayStation 5",
        "Console Sony PlayStation 5 Edição Digital Slim CFI 2114B",
    )
    assert display == "CFI-2114B"

    queries = build_search_queries(
        ProductIdentity(
            gtin=None,
            brand="sony",
            model="playstation5slimdigital",
            title=(
                "Console Sony PlayStation 5 Edição Digital Slim, SSD 825GB, "
                "Controle DualSense, Branco - CFI 2114B"
            ),
            title_normalized="console sony playstation 5 edicao digital slim",
            variant_attrs={"storage": "825gb", "color": "branco"},
            store="kabum",
            product_id="1050570",
            price=None,
            currency="BRL",
            mpn="cfi2114b",
            mpn_display="CFI-2114B",
        )
    )
    assert "CFI-2114B" in queries
    assert "sony playstation 5 digital 825gb" in queries
    assert "playstation 5 digital 825gb" in queries
    # Primary series queries must not require "slim" (title fallback may keep it).
    assert all(
        "slim" not in q
        for q in queries
        if q.startswith("sony playstation 5") or q.startswith("playstation 5")
    )


def test_marketing_noise_bluetooth_8k_does_not_block_ps5_match() -> None:
    score = MatchingEngine().score(
        _identity(
            brand="sony",
            model="playstation5digital",
            title="PlayStation 5 Edição Digital 825GB Branco",
            variant_attrs={"storage": "825gb", "color": "branco"},
            mpn="cfi2115b",
        ),
        _identity(
            brand="sony",
            model="playstation5digital",
            title=(
                "Sony PlayStation 5 Digital Edition, Ultra-High Speed 825GB SSD, "
                "WiFi 6, Bluetooth 5.1, 120Hz 8K Output, White"
            ),
            variant_attrs={"storage": "825gb", "color": "white"},
        ),
    )
    assert score.decision == "auto_match"


def test_match_stops_after_two_empty_searches() -> None:
    """Do not burn the full query list when SERP repeatedly returns []."""
    from unittest.mock import MagicMock

    from scout_api.modules.matching.product_match_service import ProductMatchService
    from scout_api.modules.matching.schemas import MatchRequest

    ref = _item(
        store="magazineluiza",
        product_id="238803400",
        title="Apple iPhone 16 128GB Preto",
        brand="Apple",
        model="iPhone 16",
        url="https://www.magazineluiza.com.br/p/238803400/",
        canonical_url="https://www.magazineluiza.com.br/p/238803400/",
        variant="Preto",
    )
    scrape = MagicMock()
    scrape.scrape.return_value = ref
    search = MagicMock()
    search.is_search_supported.return_value = True
    search.search.return_value = []

    resp = ProductMatchService(scrape_service=scrape, search_service=search).match(
        MatchRequest(
            reference_url="https://www.magazineluiza.com.br/p/238803400/",
            stores=["shopee"],
            persist=False,
        )
    )
    assert resp.unmatched_stores == ["shopee"]
    assert search.search.call_count == 2


# --- GPU / discrete graphics identity (Search vs Match) ---


def test_gpu_query_generation_progressive_not_full_title() -> None:
    """Queries prefer brand+chip+edition+VRAM over noisy SEO title heads."""
    identity = identity_from_price_item(
        _item(
            store="visaovip",
            title=(
                "Placa de Video MSI Shadow 3X OC 12GB GeForce RTX5070 GDDR7 "
                "- 912-V532-232"
            ),
            brand="MSI",
            model="Shadow 3X OC",
            sku="912-V532-232",
            variant="ram: 12 GB",
            metadata={
                "specifications": {
                    "REFERÊNCIA": "912-V532-232",
                    "MODELO": "Shadow 3X OC",
                    "gpu_model": "GeForce RTX5070",
                }
            },
        )
    )
    queries = build_search_queries(identity)
    assert queries
    # Progressive commercial ladder leads; MPN is a fallback for GPUs.
    assert any(q.casefold().startswith("msi rtx 5070 shadow 3x") for q in queries[:4])
    assert any("912-V532-232" in q for q in queries)
    # Must not lead with a long SEO dump (Ray Tracing / MHz / bus width).
    joined = " | ".join(queries).casefold()
    assert "ray tracing" not in joined
    assert "2557" not in joined
    assert "192" not in joined
    assert "dlss" not in joined
    assert queries[0].casefold().startswith("msi rtx 5070")


def test_gpu_same_product_different_titles_match() -> None:
    ref = identity_from_price_item(
        _item(
            store="visaovip",
            product_id="55359",
            title="Placa de Video MSI Shadow 3X OC 12GB GeForce RTX5070 GDDR7",
            brand="MSI",
            sku="912-V532-232",
        )
    )
    kabum = identity_from_price_item(
        _item(
            store="kabum",
            product_id="777166",
            title=(
                "MSI RTX 5070 12G Shadow 3X OC NVIDIA GeForce 12GB GDDR7 "
                "2557 MHz 192-bit FP4 and DLSS 4 Ray Tracing G5070-12S3C"
            ),
            brand="MSI",
        )
    )
    magalu = identity_from_price_item(
        _item(
            store="magazineluiza",
            product_id="fkff6cf4a2",
            title=(
                "MSI RTX 5070 12G Shadow 3X OC NVIDIA GeForce 12GB GDDR7 "
                "192bit FP4 Ray Tracing"
            ),
            brand="MSI",
        )
    )
    engine = MatchingEngine()
    for candidate in (kabum, magalu):
        score = engine.score(ref, candidate)
        assert score.decision == "auto_match", score.reasons
        assert any(r.code == "brand_match" for r in score.reasons)


def test_gpu_ti_suffix_blocks_match() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="MSI Shadow 3X OC 12GB GeForce RTX 5070 GDDR7",
                brand="MSI",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title="MSI Shadow 3X OC 12GB GeForce RTX 5070 Ti GDDR7",
                brand="MSI",
            )
        ),
    )
    assert score.decision == "reject"
    assert any(
        r.code == "critical_conflict" and "gpu_mismatch" in (r.detail or "")
        for r in score.reasons
    )


def test_gpu_vram_mismatch_blocks_match() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="MSI Shadow 3X OC 12GB GeForce RTX 5070 GDDR7",
                brand="MSI",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title="MSI Shadow 3X OC 16GB GeForce RTX 5070 GDDR7",
                brand="MSI",
            )
        ),
    )
    assert score.decision == "reject"
    assert any("vram" in (r.detail or "") for r in score.reasons)


def test_gpu_edition_mismatch_blocks_match() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="MSI Shadow 3X OC 12GB GeForce RTX 5070 GDDR7",
                brand="MSI",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title="MSI Gaming Trio OC 12GB GeForce RTX 5070 GDDR7",
                brand="MSI",
            )
        ),
    )
    assert score.decision == "reject"
    assert any("edition" in (r.detail or "") for r in score.reasons)


def test_gpu_title_noise_does_not_block_match() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="MSI RTX 5070 Shadow 3X OC 12GB GDDR7",
                brand="MSI",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title=(
                    "Placa de Video MSI RTX 5070 12G Shadow 3X OC NVIDIA GeForce "
                    "12GB GDDR7 DLSS 4 Ray Tracing 2557 MHz 192-bit FP4"
                ),
                brand="MSI",
            )
        ),
    )
    assert score.decision == "auto_match"


def test_gpu_candidate_retrieval_mock_uses_progressive_query() -> None:
    """Search layer is queried with progressive identity queries, not full title."""
    from unittest.mock import MagicMock

    from scout_api.modules.crawler.models.search import SearchCandidate
    from scout_api.modules.matching.product_match_service import ProductMatchService
    from scout_api.modules.matching.schemas import MatchRequest

    ref = _item(
        store="visaovip",
        product_id="55359",
        title="Placa de Video MSI Shadow 3X OC 12GB GeForce RTX5070 GDDR7",
        brand="MSI",
        sku="912-V532-232",
        url="https://visaovip.com/prod/x/55359/",
        canonical_url="https://visaovip.com/prod/x/55359/",
        metadata={
            "specifications": {
                "REFERÊNCIA": "912-V532-232",
                "gpu_model": "GeForce RTX5070",
            }
        },
    )
    cand_item = _item(
        store="kabum",
        product_id="777166",
        title="MSI RTX 5070 12G Shadow 3X OC NVIDIA GeForce 12GB GDDR7",
        brand="MSI",
        url="https://www.kabum.com.br/produto/777166/placa",
        canonical_url="https://www.kabum.com.br/produto/777166/placa",
    )
    scrape = MagicMock()
    scrape.scrape.side_effect = [ref, cand_item]
    search = MagicMock()
    search.is_search_supported.return_value = True

    def _search(store: str, query: str, **_kwargs: object) -> list[SearchCandidate]:
        # Identifier-only MPNs often miss; progressive commercial query hits.
        if "shadow" in query.casefold() and "5070" in query:
            return [
                SearchCandidate(
                    url=cand_item.url,
                    title=cand_item.title,
                    product_id="777166",
                    metadata={"source": "mock"},
                )
            ]
        return []

    search.search.side_effect = _search

    resp = ProductMatchService(scrape_service=scrape, search_service=search).match(
        MatchRequest(
            reference_url=ref.url,
            stores=["kabum"],
            persist=False,
        )
    )
    assert resp.matches
    assert resp.matches[0].store == "kabum"
    assert resp.matches[0].product.product_id == "777166"
    queried = [call.args[1] for call in search.search.call_args_list]
    assert any("shadow" in q.casefold() for q in queried)
    assert all("ray tracing" not in q.casefold() for q in queried)


def test_cross_category_phone_ssd_ram_console_still_match() -> None:
    """GPU changes must not break other categories."""
    engine = MatchingEngine()
    phone = engine.score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="Apple iPhone 15 128GB Blue",
                brand="Apple",
                model="iPhone 15",
                variant="color: Blue; storage: 128GB",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title="Celular Apple iPhone 15 Azul 128 GB",
                brand="Apple",
                model="iPhone 15",
                variant="color: Azul; storage: 128 GB",
            )
        ),
    )
    assert phone.decision == "auto_match"

    ssd = engine.score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="SSD Samsung 990 EVO Plus 1TB M.2 NVMe - MZ-V9S1T0B/AM",
                brand="Samsung",
                model="MZ-V9S1T0B/AM",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title="Samsung 990 EVO Plus 1TB NVMe SSD MZ-V9S1T0B/AM",
                brand="Samsung",
                model="990 EVO Plus",
            )
        ),
    )
    assert ssd.decision == "auto_match"

    ram = engine.score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="Kingston HyperX Fury DDR4 8GB",
                brand="Kingston",
                model="hx432c16fb3",
                mpn="hx432c16fb3",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title="Memoria Kingston HyperX Fury 8GB DDR4 HX432C16FB3",
                brand="Kingston",
                model="hx432c16fb3",
            )
        ),
    )
    # Prefer structured MPN when present on identity_from_price_item via sku/title.
    if ram.decision != "auto_match":
        ram = MatchingEngine().score(
            _identity(
                brand="kingston",
                model="hx432c16fb3",
                title="Kingston HyperX Fury DDR4 8GB",
                mpn="hx432c16fb3",
            ),
            _identity(
                brand="kingston",
                model="hx432c16fb3",
                title="Memoria Kingston HyperX Fury 8GB DDR4",
                mpn="hx432c16fb3",
            ),
        )
    assert ram.decision == "auto_match"

    console = engine.score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="PlayStation 5 Edição Digital 825GB",
                brand="Sony",
                model="PlayStation 5 Digital",
                variant="storage: 825GB",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title="Sony PlayStation 5 Digital Edition 825GB SSD White",
                brand="Sony",
                model="PS5 Digital",
                variant="storage: 825 GB",
            )
        ),
    )
    assert console.decision in {"auto_match", "review"}


# --- Gigabyte GeForce RTX 5060: identity-only discovery regressions ----------


def test_gigabyte_rtx5060_laptop_form_factor_rejects() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="Placa de Vídeo Gigabyte GeForce RTX 5060",
                brand="Gigabyte",
                model="GeForce RTX 5060",
            )
        ),
        identity_from_price_item(
            _item(
                store="bestbuy",
                product_id="2",
                title=(
                    'GIGABYTE - GAMING A16 - 16" 165Hz 1920x1200 WUXGA '
                    "Intel Core i7-13620H - 1TB SSD - 32GB DDR5 RAM - "
                    "GeForce RTX 5060 - Black Steel"
                ),
                brand="Gigabyte",
                model="GeForce RTX 5060",
            )
        ),
    )
    assert score.decision == "reject"
    assert any(r.code == "form_factor_reject" for r in score.reasons)


def test_gigabyte_rtx5060_same_family_different_titles_match() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="Gigabyte GeForce RTX 5060 Gaming OC",
                brand="Gigabyte",
                model="GeForce RTX 5060",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title="Gigabyte RTX 5060 Gaming OC 8GB",
                brand="Gigabyte",
                model="GeForce RTX 5060",
            )
        ),
    )
    assert score.decision == "auto_match"


def test_gigabyte_rtx5060_different_manufacturer_rejects() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="Gigabyte GeForce RTX 5060",
                brand="Gigabyte",
                model="GeForce RTX 5060",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title="MSI GeForce RTX 5060",
                brand="MSI",
                model="GeForce RTX 5060",
            )
        ),
    )
    assert score.decision == "reject"
    assert any(r.code == "brand_mismatch" for r in score.reasons)


def test_gigabyte_rtx5060_ti_suffix_rejects() -> None:
    score = MatchingEngine().score(
        identity_from_price_item(
            _item(
                store="a",
                product_id="1",
                title="Gigabyte GeForce RTX 5060",
                brand="Gigabyte",
                model="GeForce RTX 5060",
            )
        ),
        identity_from_price_item(
            _item(
                store="b",
                product_id="2",
                title="Gigabyte GeForce RTX 5060 Ti",
                brand="Gigabyte",
                model="GeForce RTX 5060 Ti",
            )
        ),
    )
    assert score.decision == "reject"
    assert any(
        r.code == "critical_conflict" and "gpu_mismatch" in (r.detail or "")
        for r in score.reasons
    )


def test_gigabyte_rtx5060_base_query_allows_multiple_editions() -> None:
    """brand+model without edition: Windforce / Gaming OC / Eagle are all candidates."""
    from dataclasses import replace

    from scout_api.modules.matching.identity import identity_reference_item

    ref = replace(
        identity_from_price_item(
            identity_reference_item(
                "Placa de Vídeo Gigabyte GeForce RTX 5060",
                category="gpu",
            )
        ),
        price=None,
    )
    assert ref.brand == "gigabyte"
    assert "5060" in (ref.model or "")
    assert "ti" not in (ref.model or "")
    assert not ref.variant_attrs.get("edition")

    queries = build_search_queries(ref)
    assert queries
    assert any("gigabyte" in q.casefold() and "5060" in q for q in queries)
    assert all("gaming oc" not in q.casefold() for q in queries)
    assert all("windforce" not in q.casefold() for q in queries)

    engine = MatchingEngine()
    for title in (
        "Placa de Vídeo Gigabyte RTX 5060 Windforce 8GB GDDR7",
        "Gigabyte GeForce RTX 5060 Gaming OC 8GB",
        "Gigabyte RTX 5060 Eagle OC 8GB GDDR7",
    ):
        score = engine.score(
            ref,
            identity_from_price_item(
                _item(store="kabum", product_id="x", title=title, brand="Gigabyte")
            ),
        )
        assert score.decision == "auto_match", (title, score.reasons)


def test_gigabyte_rtx5060_variant_specified_restricts_edition() -> None:
    ref = identity_from_price_item(
        _item(
            store="synthetic",
            product_id="identity",
            title="Gigabyte GeForce RTX 5060 Gaming OC",
            brand="Gigabyte",
            model="GeForce RTX 5060",
        )
    )
    assert ref.variant_attrs.get("edition")

    queries = build_search_queries(ref)
    assert any("gaming" in q.casefold() for q in queries)

    engine = MatchingEngine()
    gaming = engine.score(
        ref,
        identity_from_price_item(
            _item(
                store="kabum",
                product_id="1",
                title="Gigabyte RTX 5060 Gaming OC 8GB GDDR7",
                brand="Gigabyte",
            )
        ),
    )
    assert gaming.decision == "auto_match"

    windforce = engine.score(
        ref,
        identity_from_price_item(
            _item(
                store="kabum",
                product_id="2",
                title="Gigabyte RTX 5060 Windforce 8GB GDDR7",
                brand="Gigabyte",
            )
        ),
    )
    assert windforce.decision == "reject"
    assert any("edition" in (r.detail or "") for r in windforce.reasons)


def test_match_from_item_identity_only_discovers_without_reference_url() -> None:
    """Search receives progressive identity queries; no known store URL is injected."""
    from unittest.mock import MagicMock

    from scout_api.modules.crawler.models.search import SearchCandidate
    from scout_api.modules.matching.identity import identity_reference_item
    from scout_api.modules.matching.product_match_service import ProductMatchService

    reference = identity_reference_item(
        "Placa de Vídeo Gigabyte GeForce RTX 5060",
        category="gpu",
    )
    cand = _item(
        store="kabum",
        product_id="999001",
        title="Placa de Vídeo Gigabyte RTX 5060 Windforce OC 8GB GDDR7",
        brand="Gigabyte",
        model="GeForce RTX 5060",
        url="https://www.kabum.com.br/produto/999001/placa",
        canonical_url="https://www.kabum.com.br/produto/999001/placa",
    )
    scrape = MagicMock()
    scrape.scrape.return_value = cand
    search = MagicMock()
    search.is_search_supported.return_value = True

    def _search(store: str, query: str, **_kwargs: object) -> list[SearchCandidate]:
        assert "kabum.com.br" not in query.casefold()
        assert "http" not in query.casefold()
        if "gigabyte" in query.casefold() and "5060" in query:
            return [
                SearchCandidate(
                    url=cand.url,
                    title=cand.title,
                    product_id="999001",
                    metadata={"source": "mock"},
                )
            ]
        return []

    search.search.side_effect = _search
    resp = ProductMatchService(
        scrape_service=scrape, search_service=search
    ).match_from_item(
        reference,
        stores=["kabum"],
        persist=False,
    )
    assert resp.matches
    assert resp.matches[0].store == "kabum"
    assert resp.matches[0].product.product_id == "999001"
    assert resp.matches[0].product.url.startswith("https://www.kabum.com.br/")
    queried = [call.args[1] for call in search.search.call_args_list]
    assert queried
    assert all("http" not in q.casefold() for q in queried)
    # Reference scrape must not be called — only candidate URLs.
    assert all(
        "scout://identity" not in str(call.args[0])
        for call in scrape.scrape.call_args_list
    )


def test_match_early_stops_scraping_after_auto_match() -> None:
    """Once a store auto_matches, do not scrape remaining SERP candidates."""
    from unittest.mock import MagicMock

    from scout_api.modules.crawler.models.search import SearchCandidate
    from scout_api.modules.matching.identity import identity_reference_item
    from scout_api.modules.matching.product_match_service import ProductMatchService

    reference = identity_reference_item(
        "Placa de Vídeo Gigabyte GeForce RTX 5060 Windforce OC 8GB",
        category="gpu",
    )
    good = _item(
        store="kabum",
        product_id="good-1",
        title="Placa de Vídeo Gigabyte GeForce RTX 5060 Windforce OC 8GB GDDR7",
        brand="Gigabyte",
        model="GeForce RTX 5060",
        url="https://www.kabum.com.br/produto/good-1/placa",
        canonical_url="https://www.kabum.com.br/produto/good-1/placa",
    )
    scrape = MagicMock()
    scrape.scrape.return_value = good
    search = MagicMock()
    search.is_search_supported.return_value = True
    search.search.return_value = [
        SearchCandidate(
            url=good.url,
            title=good.title,
            product_id="good-1",
        ),
        SearchCandidate(
            url="https://www.kabum.com.br/produto/noise-2/placa",
            title="Placa de Vídeo Gigabyte GeForce RTX 5060 Gaming OC 8GB",
            product_id="noise-2",
        ),
        SearchCandidate(
            url="https://www.kabum.com.br/produto/noise-3/placa",
            title="Placa de Vídeo Gigabyte GeForce RTX 5060 Eagle OC 8GB",
            product_id="noise-3",
        ),
    ]

    resp = ProductMatchService(
        scrape_service=scrape, search_service=search
    ).match_from_item(
        reference,
        stores=["kabum"],
        persist=False,
        max_candidates_per_store=5,
        clear_reference_price=True,
    )
    assert resp.matches
    assert resp.matches[0].decision == "auto_match"
    assert scrape.scrape.call_count == 1


def test_match_skips_scrape_when_serp_title_clearly_conflicts() -> None:
    """Notebook SERP titles must not trigger a discrete-GPU PDP scrape."""
    from unittest.mock import MagicMock

    from scout_api.modules.crawler.models.search import SearchCandidate
    from scout_api.modules.matching.identity import identity_reference_item
    from scout_api.modules.matching.product_match_service import ProductMatchService

    reference = identity_reference_item(
        "Placa de Vídeo Gigabyte GeForce RTX 5060 8GB GDDR7",
        category="gpu",
    )
    scrape = MagicMock()
    search = MagicMock()
    search.is_search_supported.return_value = True
    search.search.return_value = [
        SearchCandidate(
            url="https://www.bestbuy.com/site/laptop-rtx-5060/123.p",
            title="ASUS TUF Gaming A15 Laptop with GeForce RTX 5060 16GB RAM",
            product_id="123",
        ),
        SearchCandidate(
            url="https://www.bestbuy.com/site/gpu-rtx-5060/456.p",
            title="Gigabyte GeForce RTX 5060 WINDFORCE OC 8G Graphics Card",
            product_id="456",
        ),
    ]
    good = _item(
        store="bestbuy",
        product_id="456",
        title="Gigabyte GeForce RTX 5060 WINDFORCE OC 8G Graphics Card",
        brand="Gigabyte",
        model="GeForce RTX 5060",
        url="https://www.bestbuy.com/site/gpu-rtx-5060/456.p",
        canonical_url="https://www.bestbuy.com/site/gpu-rtx-5060/456.p",
        country="US",
        currency="USD",
    )
    scrape.scrape.return_value = good

    resp = ProductMatchService(
        scrape_service=scrape, search_service=search
    ).match_from_item(
        reference,
        stores=["bestbuy"],
        persist=False,
        max_candidates_per_store=5,
        clear_reference_price=True,
    )
    assert scrape.scrape.call_count == 1
    assert scrape.scrape.call_args.args[0] == good.url
    assert resp.matches
    assert resp.matches[0].product.product_id == "456"
