"""Inspect Terabyte specs markup and price DOM ids."""

from __future__ import annotations

import re
from pathlib import Path

raw = Path("memory/working/_terabyte_probe/espec_tecnicas.html").read_text(
    encoding="utf-8", errors="replace"
)
idx = raw.casefold().find("marca")
print("SPECS MARKUP AROUND Marca:")
print(repr(raw[idx : idx + 900]))
print("---")

full = Path("memory/working/_terabyte_probe/curl_cffi_clean.html").read_text(
    encoding="utf-8", errors="replace"
)
for pat in (
    "valVista",
    "valParc",
    "parcelamento",
    "box-preco",
    "p-price",
    "price-box",
    "vista",
    "juros",
):
    print(f"count[{pat}]={full.casefold().count(pat.casefold())}")

ids = re.findall(
    r"""id=["']([^"']*(?:preco|price|vista|parc|valor|prod)[^"']*)["']""",
    full,
    re.I,
)
print("price-ish ids:", sorted(set(ids))[:40])

classes = re.findall(
    r"""class=["']([^"']*(?:preco|price|vista|parc)[^"']*)["']""",
    full,
    re.I,
)
print("price-ish classes sample:", sorted(set(classes))[:40])

# Find installment JS
for m in re.finditer(r".{0,60}parcel.{0,120}", full, re.I):
    snip = re.sub(r"\s+", " ", m.group(0))
    if any(ch.isdigit() for ch in snip):
        print("parcel ctx:", snip[:200])

# Look near JSON-LD price vs visible
for m in re.finditer(r"R\$\s*[0-9\.\,]+", full):
    ctx = full[max(0, m.start() - 60) : m.end() + 80]
    ctx = re.sub(r"\s+", " ", ctx)
    if "vista" in ctx.casefold() or "pix" in ctx.casefold() or "de " in ctx.casefold():
        print("money ctx:", ctx[:220])
