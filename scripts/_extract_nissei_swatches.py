"""Extract main-product swatch options and contentsWithIds from Nissei HTML."""

from __future__ import annotations

import json
import re
from pathlib import Path

OUT = Path("data/nissei_variant_diag")


def extract_balanced(text: str, start: int) -> str | None:
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, min(len(text), start + 5_000_000)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def main() -> None:
    for i, label in enumerate(["A", "B"]):
        text = (OUT / f"page_{i}.html").read_text(encoding="utf-8")
        print("=" * 50, label)

        # Main product media / info region roughly: from product-info-main
        start = text.find('class="product-info-main"')
        if start < 0:
            start = text.find("product-info-main")
        end = text.find("product-social-links", start) if start >= 0 else -1
        if start < 0:
            region = text
            print("no product-info-main; using full page")
        else:
            if end < 0:
                end = start + 80000
            region = text[start:end]
            print("product-info-main region", len(region), "start", start)

        # All swatch attributes in region
        for m in re.finditer(
            r'data-attribute-code="([^"]+)"[^>]*data-attribute-id="([^"]+)"',
            region,
        ):
            code, aid = m.group(1), m.group(2)
            # find options until next swatch-attribute or end
            chunk = region[m.start() : m.start() + 15000]
            opts = re.findall(
                r'data-option-id="(\d+)"[^>]*data-option-label="([^"]+)"'
                r"|data-option-label=\"([^\"]+)\"[^>]*data-option-id=\"(\d+)\"",
                chunk,
            )
            # normalize
            parsed = []
            for a, b, c, d in opts:
                if a:
                    parsed.append((a, b))
                else:
                    parsed.append((d, c))
            # stop at next attribute roughly by unique option ids early
            print(f"ATTR {code} id={aid} options={parsed[:20]} count={len(parsed)}")

            selected = re.search(
                r'data-option-selected="(\d+)"|option-selected="(\d+)"',
                chunk[:2000],
            )
            print("  selected-attr", selected.groups() if selected else None)
            label_el = re.search(
                r'class="swatch-attribute-selected-option"[^>]*>(.*?)<',
                chunk[:2000],
                flags=re.S,
            )
            print(
                "  selected-label",
                (label_el.group(1).strip() if label_el else None),
            )

        # contentsWithIds
        for needle in ("contentsWithIds", "content_with_ids", "skuData"):
            idx = text.find(needle)
            print(needle, "at", idx)
            if idx >= 0:
                print(text[idx : idx + 400])

        # Look for JSON-like maps of product ids near updateProductData
        idx = text.find("updateProductData")
        if idx >= 0:
            print("updateProductData context", text[idx - 200 : idx + 600])

        # Magento form key / product id hidden inputs
        for m in re.finditer(
            r'<input[^>]+name="product"[^>]*>|<input[^>]+type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"',
            region,
            flags=re.I,
        ):
            print("input", m.group(0)[:200])

        # Related child product links on page pointing to variant URLs
        links = re.findall(
            r'href="(https://nissei\.com/br/samsung-galaxy-s25-ultra[^"]+)"',
            text,
        )
        uniq = sorted(set(links))
        print("s25 ultra links", len(uniq))
        for u in uniq[:20]:
            print(" ", u)

        # Try GraphQL endpoint probe patterns in page
        for m in re.finditer(r"graphql|/rest/V1/products", text, flags=re.I):
            print("api mention", text[m.start() : m.start() + 100])
            break

        # Price box for main product
        price_box = re.search(
            r'price-box[^>]*data-product-id="(\d+)"[\s\S]{0,500}?data-price-amount="([^"]+)"',
            region,
        )
        if price_box:
            print("main price-box", price_box.group(1), price_box.group(2))

        # JSON-LD full dump of Product
        for m in re.finditer(
            r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
            text,
            flags=re.I | re.S,
        ):
            raw = m.group(1).strip()
            try:
                ld = json.loads(raw)
            except json.JSONDecodeError:
                continue
            items = ld if isinstance(ld, list) else [ld]
            for it in items:
                if isinstance(it, dict) and it.get("@type") in {
                    "Product",
                    "ProductGroup",
                }:
                    path = OUT / f"jsonld_{i}.json"
                    path.write_text(
                        json.dumps(it, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    print("jsonld saved", path, "keys", list(it.keys()))


if __name__ == "__main__":
    main()
