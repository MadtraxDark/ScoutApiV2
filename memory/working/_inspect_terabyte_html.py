"""Inspect Terabyte PDP HTML sources (JSON-LD, specs, price, images)."""

from __future__ import annotations

import json
import re
from pathlib import Path

html = Path("memory/working/_terabyte_probe/curl_cffi_clean.html").read_text(
    encoding="utf-8", errors="replace"
)
print("len", len(html))

blocks = re.findall(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    html,
    re.I | re.S,
)
print("ld+json blocks", len(blocks))
for i, block in enumerate(blocks[:8]):
    try:
        data = json.loads(block)
    except Exception as exc:
        print(f" block{i} parse fail {exc} snippet={block[:180]!r}")
        continue
    if isinstance(data, list):
        print(f" block{i} list len={len(data)}")
        data = data[0] if data and isinstance(data[0], dict) else {}
    if not isinstance(data, dict):
        print(f" block{i} type={type(data).__name__}")
        continue
    t = data.get("@type")
    print(f" block{i} @type={t} keys={list(data)[:15]}")
    if t == "Product" or (isinstance(t, list) and "Product" in t):
        print("  name=", data.get("name"))
        print("  sku=", data.get("sku"))
        print("  productID=", data.get("productID") or data.get("productId"))
        print("  brand=", data.get("brand"))
        print("  mpn=", data.get("mpn"))
        print("  gtin=", data.get("gtin") or data.get("gtin13") or data.get("gtin14"))
        offers = data.get("offers")
        print("  offers=", json.dumps(offers, ensure_ascii=False)[:500])
        img = data.get("image")
        if isinstance(img, list):
            print("  images", len(img), "first", img[0] if img else None)
        else:
            print("  image", img)
        if data.get("additionalProperty"):
            print("  additionalProperty", data.get("additionalProperty")[:5])
        if data.get("description"):
            print("  description_len", len(str(data.get("description"))))

# Specs probes
folded = html.casefold()
for pat in (
    "especifica",
    "ficha",
    "técnic",
    "tecnic",
    "característ",
    "caracterist",
    "additionalproperty",
    "tabela",
    "spec-list",
    "box-espec",
    "descricao",
):
    print(f"count[{pat}]={folded.count(pat)}")

idx = folded.find("especifica")
print("first especifica idx", idx)
if idx >= 0:
    print("--- snippet ---")
    print(html[idx : idx + 1200])

# Look for table rows near specs
for m in re.finditer(r"<table[^>]{0,120}class=[\"'][^\"']*espec", html, re.I):
    print("table match", m.group(0)[:200])

# Pix / parcelamento
for pat in ("pix", "à vista", "a vista", "parcel", "sem juros", "x de"):
    print(f"money-ish[{pat}]={folded.count(pat)}")

# Inline product state
for pat in (
    r"['\"]price['\"]\s*:\s*([0-9]+(?:\.[0-9]+)?)",
    r"['\"]preco['\"]\s*:\s*([0-9]+(?:\.[0-9]+)?)",
    r"['\"]avista['\"]\s*:\s*([0-9]+(?:\.[0-9]+)?)",
    r"product_id['\"]?\s*[:=]\s*['\"]?(\d+)",
):
    found = re.findall(pat, html, re.I)
    print(pat, "→", found[:8])

# OpenGraph
for prop in ("og:title", "og:image", "product:price:amount", "product:brand"):
    m = re.search(
        rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
        html,
        re.I,
    )
    if not m:
        m = re.search(
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}',
            html,
            re.I,
        )
    print(prop, "→", m.group(1) if m else None)

# Gallery selectors common on Magento-ish
for sel in (
    "gallery",
    "fotorama",
    "cloud-zoom",
    "product-image",
    "owl-carousel",
    "data-zoom-image",
):
    print(f"gallery[{sel}]={folded.count(sel)}")
