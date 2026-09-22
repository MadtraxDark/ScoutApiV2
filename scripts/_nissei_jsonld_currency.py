"""Inspect JSON-LD and currency markers on saved Nissei pages."""

from __future__ import annotations

import json
import re
from pathlib import Path

OUT = Path("data/nissei_variant_diag")


def main() -> None:
    for i in (0, 1):
        text = (OUT / f"page_{i}.html").read_text(encoding="utf-8")
        print("=" * 40, i)
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
                if isinstance(it, dict):
                    print("type", it.get("@type"), "keys", list(it.keys())[:25])
                    print(json.dumps(it, ensure_ascii=False)[:1000])
        for needle in ("USD", "PYG", "Gs.", "currency", "U$"):
            print(needle, text.find(needle))
        # visible price near price-box
        m = re.search(
            r'data-price-type="finalPrice"[\s\S]{0,300}?class="price"[^>]*>(.*?)<',
            text,
        )
        print("visible price", m.group(1).strip() if m else None)
        m = re.search(r'"priceCurrency"\s*:\s*"([^"]+)"', text)
        print("priceCurrency", m.group(1) if m else None)


if __name__ == "__main__":
    main()
