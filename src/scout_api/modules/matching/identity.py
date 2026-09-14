"""Identity normalization helpers for product matching."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from scout_api.modules.crawler.models.product import ProductPriceItem

VARIANT_GATE_KEYS = frozenset({"color", "storage", "size", "capacity", "ram", "pack"})

# Map common PT/EN/ES color labels to a single canonical token for gates.
COLOR_CANONICAL: dict[str, str] = {
    "preto": "black",
    "black": "black",
    "negro": "black",
    "noir": "black",
    "branco": "white",
    "white": "white",
    "blanco": "white",
    "blanc": "white",
    "azul": "blue",
    "blue": "blue",
    "vermelho": "red",
    "red": "red",
    "rojo": "red",
    "verde": "green",
    "green": "green",
    "dourado": "gold",
    "gold": "gold",
    "rose gold": "rosegold",
    "rosegold": "rosegold",
    "ouro rosa": "rosegold",
    "prateado": "silver",
    "prata": "silver",
    "silver": "silver",
    "cinza": "gray",
    "cinza espacial": "gray",
    "space gray": "gray",
    "space grey": "gray",
    "luna grey": "gray",
    "luna gray": "gray",
    "arctic grey": "gray",
    "arctic gray": "gray",
    "platinum grey": "gray",
    "platinum gray": "gray",
    "storm grey": "gray",
    "storm gray": "gray",
    "gray": "gray",
    "grey": "gray",
    "rosa": "pink",
    "pink": "pink",
    "roxo": "purple",
    "purple": "purple",
    "lavanda": "lavender",
    "lavender": "lavender",
    "titanio": "titanium",
    "titanium": "titanium",
}

# Trailing marketing noise stripped before soft model comparison.
_MODEL_NOISE_SUFFIXES: tuple[str, ...] = (
    "everydaylaptop",
    "intelcore",
    "amdryzen",
    "windows11",
    "windows10",
    "processor",
    "laptop",
    "notebook",
)

_MODEL_FAMILY_MARKERS: tuple[str, ...] = (
    "ideapad",
    "thinkpad",
    "iphone",
    "galaxy",
    "macbook",
    "vivobook",
    "pavilion",
    "inspiron",
    "nitro",
    "legion",
)

# When metadata stores RAM as "storage", prefer SSD-sized capacities from title.
_RAM_LIKE_MAX_GB = 64
_STORAGE_LIKE_MIN_GB = 128

ACCESSORY_TOKENS = frozenset(
    {
        "capa",
        "case",
        "pelicula",
        "película",
        "cabo",
        "carregador",
        "charger",
        "suporte",
        "cover",
        "skin",
        "protetor",
        "film",
        "adapter",
        "adaptador",
        "bolsa",
        "pouch",
    }
)

TITLE_STOPWORDS = frozenset(
    {
        "oferta",
        "promo",
        "promocao",
        "promoção",
        "frete",
        "gratis",
        "grátis",
        "envio",
        "novo",
        "nova",
        "original",
        "oficial",
        "kit",
        "com",
        "para",
        "the",
        "and",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "em",
        "na",
        "no",
        "a",
        "o",
        "e",
        "ou",
    }
)


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_only.casefold().strip()


def gtin_check_digit(body: str) -> str:
    """Compute GTIN check digit for an 7/11/12/13-digit body (without check)."""
    digits = [int(ch) for ch in body]
    total = 0
    # From right: odd positions weight 3, even weight 1 (GS1).
    for index, digit in enumerate(reversed(digits)):
        total += digit * (3 if index % 2 == 0 else 1)
    return str((10 - (total % 10)) % 10)


def normalize_gtin(raw: str | None) -> str | None:
    """Normalize EAN/UPC/GTIN to digits with valid check digit when possible."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    if len(digits) == 12:
        digits = f"0{digits}"
    if len(digits) == 8:
        # GTIN-8 — validate as-is
        body, check = digits[:-1], digits[-1]
        if gtin_check_digit(body) != check:
            return None
        return digits
    if len(digits) == 13:
        body, check = digits[:-1], digits[-1]
        if gtin_check_digit(body) != check:
            return None
        return digits
    if len(digits) == 14:
        body, check = digits[:-1], digits[-1]
        if gtin_check_digit(body) != check:
            return None
        return digits
    return None


def normalize_brand(raw: str | None) -> str | None:
    if not raw:
        return None
    folded = fold_text(raw)
    folded = re.sub(r"[^a-z0-9]+", " ", folded).strip()
    if not folded:
        return None
    # Marketplace placeholders must not hard-reject real brand matches.
    if folded in {
        "outros",
        "other",
        "others",
        "generico",
        "n a",
        "na",
        "amazon renewed store",
        "amazon renewed",
        "renewed",
    }:
        return None
    return folded


def normalize_model(raw: str | None) -> str | None:
    if not raw:
        return None
    folded = fold_text(raw)
    folded = re.sub(r"[^a-z0-9]+", "", folded)
    return folded or None


def compact_model(model: str) -> str:
    """Strip trailing marketing/CPU noise for soft model comparison."""
    current = model
    changed = True
    while changed:
        changed = False
        for suffix in _MODEL_NOISE_SUFFIXES:
            if current.endswith(suffix) and len(current) - len(suffix) >= 6:
                current = current[: -len(suffix)]
                changed = True
                break
    return current


def _cpu_family(model: str) -> str | None:
    if "ryzen" in model or "amd" in model:
        return "amd"
    if "intel" in model:
        return "intel"
    return None


def _cpu_family_from_text(text: str | None) -> str | None:
    """Detect AMD vs Intel from model/title marketing copy."""
    folded = fold_text(text or "")
    if not folded:
        return None
    if re.search(r"\b(ryzen|amd)\b", folded):
        return "amd"
    if re.search(
        r"\bintel\b|\bcore\s*(?:ultra|i[3579]|[3579])\b",
        folded,
    ):
        return "intel"
    return None


def _cpu_signature(text: str | None) -> str | None:
    """Normalize a concrete CPU SKU from title/model when present."""
    folded = fold_text(text or "")
    if not folded:
        return None
    match = re.search(r"\bi([3579])-(\d{4,5}[a-z]*)\b", folded)
    if match:
        return f"i{match.group(1)}-{match.group(2)}"
    match = re.search(r"\b(?:core\s*)?i([3579])\s*-?\s*(n\d{3}[a-z]*)\b", folded)
    if match:
        return f"i{match.group(1)}-{match.group(2)}"
    match = re.search(r"\bcore\s*([3579])\s+(\d{3}[a-z]*)\b", folded)
    if match:
        return f"core{match.group(1)}-{match.group(2)}"
    match = re.search(r"\bryzen\s*([3579])\s+(\d{4}[a-z]*)\b", folded)
    if match:
        return f"ryzen{match.group(1)}-{match.group(2)}"
    return None


def _model_has_family(model: str) -> bool:
    return any(marker in model for marker in _MODEL_FAMILY_MARKERS)


def models_compatible(
    left: str | None,
    right: str | None,
    *,
    left_title: str | None = None,
    right_title: str | None = None,
) -> bool:
    """True when model tokens refer to the same product line (not opaque SKUs)."""
    if not left or not right:
        return False
    left_blob = f"{left} {left_title or ''}".strip()
    right_blob = f"{right} {right_title or ''}".strip()
    family_a = _cpu_family(left) or _cpu_family_from_text(left_blob)
    family_b = _cpu_family(right) or _cpu_family_from_text(right_blob)
    if family_a and family_b and family_a != family_b:
        return False
    sig_a = _cpu_signature(left_blob)
    sig_b = _cpu_signature(right_blob)
    if sig_a and sig_b and sig_a != sig_b:
        return False
    if left == right:
        return True
    a, b = compact_model(left), compact_model(right)
    if a == b:
        return True
    # Naming drift: IdeaPad Slim 3 vs Slim 3i
    if a + "i" == b or b + "i" == a:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) < 10 or not longer.startswith(shorter):
        return False
    rest = longer[len(shorter) :]
    if not rest:
        return True
    if rest[0].isdigit():
        # Different chassis / generation code (e.g. …3 + 15irh10…)
        return False
    return rest in {"i", "pro", "plus", "max", "air", "ultra"}


def infer_model_from_title(title: str | None) -> str | None:
    """Best-effort model token from title when structured model is missing."""
    folded = fold_text(title or "")
    if not folded:
        return None
    match = re.search(
        r"\biphone\s*(1[0-9]|[6-9])(?:\s*(pro\s*max|pro|plus|e))?\b",
        folded,
    )
    if match:
        suffix = (match.group(2) or "").replace(" ", "")
        return normalize_model(f"iphone {match.group(1)}{suffix}")
    match = re.search(r"\bideapad\s*slim\s*(\d+i?)\b", folded)
    if match:
        return normalize_model(f"ideapad slim {match.group(1)}")
    return None


def resolve_model(raw_model: str | None, title: str | None) -> str | None:
    """Prefer family-bearing model strings; fall back to title inference for SKUs."""
    structured = normalize_model(raw_model)
    inferred = infer_model_from_title(title)
    if structured and _model_has_family(structured):
        return structured
    if inferred:
        return inferred
    return structured


def _canonical_color(text: str) -> str:
    if text in COLOR_CANONICAL:
        return COLOR_CANONICAL[text]
    words = text.split()
    # "luna grey" / "arctic gray" → match longest known suffix.
    for index in range(len(words)):
        suffix = " ".join(words[index:])
        if suffix in COLOR_CANONICAL:
            return COLOR_CANONICAL[suffix]
    return text


def normalize_variant_value(key: str, value: str) -> str:
    """Canonicalize variant values so gates compare apples-to-apples."""
    text = fold_text(value)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return text
    if key in {"storage", "capacity", "ram", "size"}:
        # "256 gb" / "256GB" → "256gb"
        compacted = re.sub(r"\s+", "", text)
        match = re.fullmatch(r"(\d+)(gb|tb|mb|mm|cm|in|\"|')?", compacted)
        if match:
            unit = match.group(2) or ""
            return f"{match.group(1)}{unit}"
        return compacted
    if key == "color":
        return _canonical_color(text)
    return text


def _capacity_gb(value: str) -> int | None:
    match = re.fullmatch(r"(\d+)(gb|tb)?", value)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2) or "gb"
    if unit == "tb":
        return amount * 1024
    if unit == "gb":
        return amount
    return None


def _storage_like_from_title(title: str | None) -> str | None:
    """Pick the largest SSD/HDD-like capacity mentioned in the title."""
    best: tuple[int, str] | None = None
    for amount_s, unit in re.findall(
        r"\b(\d+)\s*(gb|tb)\b",
        fold_text(title or ""),
        flags=re.I,
    ):
        amount = int(amount_s)
        unit_n = unit.lower()
        gb = amount * 1024 if unit_n == "tb" else amount
        if gb < _STORAGE_LIKE_MIN_GB and unit_n != "tb":
            continue
        token = normalize_variant_value("storage", f"{amount}{unit_n}")
        if best is None or gb > best[0]:
            best = (gb, token)
    return best[1] if best else None


def refine_storage_attrs(attrs: dict[str, str], title: str | None) -> None:
    """Replace RAM-sized 'storage' with SSD capacity inferred from the title."""
    title_storage = _storage_like_from_title(title)
    if not title_storage:
        return
    current = attrs.get("storage")
    if current is None:
        attrs["storage"] = title_storage
        return
    current_gb = _capacity_gb(current)
    if current_gb is not None and current_gb <= _RAM_LIKE_MAX_GB:
        attrs["storage"] = title_storage


def parse_variant_attributes(
    variant: str | None,
    *,
    specifications: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Parse `color: …; storage: …` variant strings plus optional specs."""
    attrs: dict[str, str] = {}
    if variant:
        for part in variant.split(";"):
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            key_n = fold_text(key).replace(" ", "_")
            if key_n and value.strip():
                # Keep language-local color tokens for search; compact storage now.
                if key_n in {"storage", "capacity", "ram", "size"}:
                    attrs[key_n] = normalize_variant_value(key_n, value)
                else:
                    text = fold_text(value)
                    text = re.sub(r"\s+", " ", text).strip()
                    if text:
                        attrs[key_n] = text
    for source in (specifications or {}, extra or {}):
        for key, value in source.items():
            if value is None:
                continue
            key_n = fold_text(str(key)).replace(" ", "_")
            if key_n not in VARIANT_GATE_KEYS and key_n not in {
                "colour",
                "cor",
                "armazenamento",
                "tamanho",
            }:
                continue
            if key_n in {"colour", "cor"}:
                key_n = "color"
            if key_n in {"armazenamento"}:
                key_n = "storage"
            if key_n in {"tamanho"}:
                key_n = "size"
            text = str(value).strip()
            if not text or text.lower() == "none":
                continue
            if key_n not in attrs:
                if key_n in {"storage", "capacity", "ram", "size"}:
                    attrs[key_n] = normalize_variant_value(key_n, text)
                else:
                    folded = fold_text(text)
                    folded = re.sub(r"\s+", " ", folded).strip()
                    if folded:
                        attrs[key_n] = folded
    # Keep only gate-relevant keys for matching.
    return {k: v for k, v in attrs.items() if k in VARIANT_GATE_KEYS}


def variants_equal(key: str, left: str, right: str) -> bool:
    """Compare variant values with canonicalization (storage units, color synonyms)."""
    return normalize_variant_value(key, left) == normalize_variant_value(key, right)


def variant_key(attrs: dict[str, str]) -> str | None:
    if not attrs:
        return None
    return "|".join(f"{k}={attrs[k]}" for k in sorted(attrs))


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    folded = fold_text(title)
    folded = re.sub(r"[^a-z0-9\s]+", " ", folded)
    tokens = [t for t in folded.split() if t and t not in TITLE_STOPWORDS]
    return " ".join(tokens)


def title_tokens(title: str | None) -> set[str]:
    return {t for t in normalize_title(title).split() if t}


def token_set_ratio(a: str | None, b: str | None) -> float:
    """Order-insensitive token overlap ratio in [0, 1]."""
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / max(len(ta), len(tb))


def looks_like_accessory(title: str | None, *, reference_title: str | None) -> bool:
    """True when candidate title looks like an accessory of the reference product."""
    cand = title_tokens(title)
    ref = title_tokens(reference_title)
    if not cand:
        return False
    has_accessory = bool(cand & ACCESSORY_TOKENS)
    ref_has_accessory = bool(ref & ACCESSORY_TOKENS)
    return has_accessory and not ref_has_accessory


@dataclass(frozen=True)
class ProductIdentity:
    gtin: str | None
    brand: str | None
    model: str | None
    title: str
    title_normalized: str
    variant_attrs: dict[str, str] = field(default_factory=dict)
    store: str | None = None
    product_id: str | None = None
    price: Decimal | None = None
    currency: str | None = None

    @property
    def variant_key(self) -> str | None:
        return variant_key(self.variant_attrs)


def identity_from_price_item(item: ProductPriceItem) -> ProductIdentity:
    meta = item.metadata if isinstance(item.metadata, dict) else {}
    raw_specs = meta.get("specifications")
    specs: dict[str, Any] = raw_specs if isinstance(raw_specs, dict) else {}
    extra: dict[str, Any] = {}
    for key in ("color", "storage", "size", "capacity", "ram"):
        value = meta.get(key)
        if (
            value is not None
            and str(value).strip()
            and str(value).strip().lower() != "none"
        ):
            extra[key] = value
    # Bare Magalu-style variant ("Preto") → treat as color when no key:value form.
    variant = item.variant
    if variant and ":" not in variant and "color" not in extra:
        extra["color"] = variant
    # Pull storage tokens from title when structured variant lacks them.
    attrs = parse_variant_attributes(
        variant if variant and ":" in variant else None,
        specifications=specs,
        extra=extra,
    )
    refine_storage_attrs(attrs, item.title)
    model = resolve_model(item.model, item.title)
    brand = normalize_brand(item.brand)
    if brand is None:
        # Title often starts with the real brand when PDP brand is a placeholder.
        title_brand = fold_text((item.title or "").split(" ")[0] if item.title else "")
        if title_brand and title_brand not in {"iphone", "galaxy", "smartphone"}:
            brand = normalize_brand(title_brand)
        if brand is None and "iphone" in fold_text(item.title or ""):
            brand = "apple"
    return ProductIdentity(
        gtin=normalize_gtin(item.gtin),
        brand=brand,
        model=model,
        title=item.title,
        title_normalized=normalize_title(item.title),
        variant_attrs=attrs,
        store=item.store,
        product_id=item.product_id,
        price=item.price,
        currency=item.currency,
    )


def build_search_queries(identity: ProductIdentity) -> list[str]:
    """Ordered search queries: GTIN → brand+model(+variant) → title tokens."""
    queries: list[str] = []
    if identity.gtin:
        queries.append(identity.gtin)
    parts = [p for p in (identity.brand, identity.model) if p]
    for key in ("storage", "color", "size", "capacity"):
        value = identity.variant_attrs.get(key)
        if value:
            parts.append(value)
    brand_model = " ".join(parts).strip()
    if brand_model and brand_model not in queries:
        queries.append(brand_model)
    tokens = identity.title_normalized.split()
    if tokens:
        title_q = " ".join(tokens[:8])
        if title_q and title_q not in queries:
            queries.append(title_q)
    return queries
