"""Identity normalization helpers for product matching."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from scout_api.modules.crawler.models.product import ProductPriceItem
from scout_api.modules.crawler.utils.product_identity import (
    canonical_variant_key,
    extract_gpu_chip,
    parse_title_identity,
)

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
    # Apple BR marketing labels for iPhone 16 palette.
    "verde acinzentado": "teal",
    "verde-acinzentado": "teal",
    "verde acizentado": "teal",
    "verde-acizentado": "teal",
    "teal": "teal",
    "ultramarino": "ultramarine",
    "ultramarine": "ultramarine",
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

# Locale / marketplace aliases → VARIANT_GATE_KEYS (applied before gate filter).
_VARIANT_KEY_ALIASES: dict[str, str] = {
    "colour": "color",
    "cor": "color",
    "color": "color",
    "armazenamento": "storage",
    "capacidade": "storage",
    "capacidade_de_armazenamento": "storage",
    "memoria_interna": "storage",
    "memoria": "storage",
    "internal_storage": "storage",
    "storage": "storage",
    "capacity": "capacity",
    "tamanho": "size",
    "size": "size",
    "ram": "ram",
    "memoria_ram": "ram",
    "pack": "pack",
    "embalagem": "pack",
}

# Preferred cross-locale color labels for progressive SERP queries.
_COLOR_SEARCH_SYNONYMS: dict[str, tuple[str, ...]] = {
    "black": ("black", "preto", "negro"),
    "white": ("white", "branco", "blanco"),
    "blue": ("blue", "azul"),
    "red": ("red", "vermelho", "rojo"),
    "green": ("green", "verde"),
    "teal": ("teal", "verde acinzentado"),
    "ultramarine": ("ultramarine", "ultramarino"),
    "pink": ("pink", "rosa"),
    "purple": ("purple", "roxo"),
    "gray": ("gray", "cinza", "grey"),
    "gold": ("gold", "dourado"),
    "silver": ("silver", "prata", "prateado"),
}

_CONDITION_TOKENS = frozenset(
    {
        "renewed",
        "refurbished",
        "recondicionado",
        "recondicionada",
        "usado",
        "usada",
        "used",
        "cpo",
        "open box",
        "open-box",
        "seminovo",
        "seminova",
    }
)

# iPhone 16e must win over bare "16"; allow glued suffix (16e) and spaced trims.
_IPHONE_MODEL_RE = re.compile(
    r"\biphone\s*(1[0-9]e|[6-9]e|1[0-9]|[6-9])(?:\s*(pro\s*max|pro|plus))?\b",
)

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
    "evoplus",
    "evopro",
    "playstation",
    "rtx",
    "gtx",
)

# Manufacturer part-number shapes frequently published in titles / model fields.
_MPN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmz[-\s]?[a-z]\d[a-z0-9]{4,}(?:/[a-z]{2})?\b"),  # Samsung SSD
    re.compile(r"\bcfi[-\s]?\d{4}[a-z]?\b"),  # PlayStation SKU
    re.compile(r"\bhx\d{3}[a-z0-9]{4,}\b"),  # Kingston HyperX
    # MSI / board-style PNs (e.g. 912-V532-232) and GPU marketing codes
    # (e.g. G5070-12S3C). Generic alnum+hyphen forms — not store-specific.
    re.compile(r"\b\d{3}-v\d{3}-\d{3}\b"),
    re.compile(r"\bg\d{4}-\d{1,2}[a-z0-9]{2,4}\b"),
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

# Extra merchandise bundled with the core SKU (reject when reference is bare).
# Pack-in copy (Astro's Playroom on every PS5 Slim) and marketing tokens
# (Bluetooth / 8K / DualSense singular) are NOT bundle markers.
_BUNDLE_MARKERS: tuple[str, ...] = (
    "smartwatch",
    "apple watch",
    "airpods",
    "bundle",
    "kit ",
    " combo",
    "com fone",
    "com watch",
    "+ watch",
    "+ airpods",
    "fortnite",
    "gran turismo",
    "astro bot",
    "spider-man",
    "spiderman",
    "wolverine",
    "god of war",
    "horizon forbidden",
    "com 2 jogos",
    "2 jogos",
    "+ jogo",
    "+ game",
    "two games",
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
        # GPU / PDP marketing noise — presence on one listing must not veto match.
        "nvidia",
        "geforce",
        "radeon",
        "placa",
        "video",
        "vídeo",
        "dlss",
        "ray",
        "tracing",
        "fp4",
        "pcie",
        "pci",
        "express",
        "mhz",
        "gbps",
        "bit",
        "displayport",
        "hdmi",
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


def normalize_mpn(raw: str | None) -> str | None:
    """Collapse manufacturer part numbers to a comparable alphanumeric token."""
    if not raw:
        return None
    return normalize_model(raw)


def _format_cfi_mpn_display(normalized: str) -> str | None:
    """Rebuild ``CFI-2115B`` from compacted ``cfi2115b`` for SERP queries."""
    match = re.fullmatch(r"cfi(\d{4})([a-z]?)", normalized)
    if not match:
        return None
    return f"CFI-{match.group(1)}{match.group(2).upper()}"


def _format_samsung_mpn_display(normalized: str) -> str | None:
    """Rebuild ``MZ-V9S1T0B/AM`` style from a compacted token for SERP queries."""
    if not normalized.startswith("mz") or len(normalized) < 10:
        return None
    body = normalized[2:]
    if len(body) >= 2 and body[-2:] in {"am", "eu", "ap"}:
        return f"MZ-{body[:-2].upper()}/{body[-2:].upper()}"
    return f"MZ-{body.upper()}"


def extract_mpn_forms(*texts: str | None) -> tuple[str | None, str | None]:
    """Return ``(normalized, display)`` MPN forms for matching vs SERP queries.

    Amazon and other retailers rank hyphenated manufacturer PNs
    (``MZ-V9S1T0B/AM``) far above compacted tokens (``mzv9s1t0bam``).
    """
    forms = extract_all_mpn_forms(*texts)
    if not forms:
        return None, None
    return forms[0]


def extract_all_mpn_forms(*texts: str | None) -> list[tuple[str, str]]:
    """Return every distinct ``(normalized, display)`` MPN found in texts.

    Board numbers and marketing model codes often co-occur for the same SKU
    (e.g. ``912-V532-232`` and ``G5070-12S3C``). Collecting all of them keeps
    SERP queries and exact-MPN matching generic without hardcoding pairs.
    """
    parts = [part for part in texts if part]
    if not parts:
        return []
    joined = " ".join(parts)
    folded = fold_text(joined)
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    raw_patterns = (
        re.compile(r"\bMZ[-\s]?[A-Za-z]\d[A-Za-z0-9]{4,}(?:/[A-Za-z]{2})?\b"),
        re.compile(r"\bCFI[-\s]?\d{4}[A-Za-z]?\b"),
        re.compile(r"\bHX\d{3}[A-Za-z0-9]{4,}\b"),
        re.compile(r"\b\d{3}-V\d{3}-\d{3}\b", re.IGNORECASE),
        re.compile(r"\bG\d{4}-\d{1,2}[A-Za-z0-9]{2,4}\b", re.IGNORECASE),
    )
    for pattern in _MPN_PATTERNS:
        for match in pattern.finditer(folded):
            normalized = normalize_mpn(match.group(0))
            if not normalized or len(normalized) < 8 or normalized in seen:
                continue
            display: str | None = None
            for raw_pattern in raw_patterns:
                for raw_match in raw_pattern.finditer(joined):
                    if normalize_mpn(raw_match.group(0)) != normalized:
                        continue
                    display = raw_match.group(0).strip().upper().replace(" ", "")
                    if "/" not in display and normalized.startswith("mz"):
                        display = _format_samsung_mpn_display(normalized) or display
                    if normalized.startswith("cfi"):
                        display = _format_cfi_mpn_display(normalized) or display
                    break
                if display is not None:
                    break
            if display is None:
                display = (
                    _format_samsung_mpn_display(normalized)
                    or _format_cfi_mpn_display(normalized)
                    or match.group(0).upper()
                )
            seen.add(normalized)
            found.append((normalized, display))
    return found


def extract_mpn(*texts: str | None) -> str | None:
    """Pull a normalized manufacturer PN from model/title text when present."""
    normalized, _display = extract_mpn_forms(*texts)
    return normalized


def model_search_phrase(*, model: str | None, title: str | None) -> str | None:
    """Human-spaced commercial model for SERP (not the compacted identity token)."""
    folded = fold_text(title or "")
    match = re.search(
        r"\b([89]\d0)\s*(evo\s*plus|evo\s*pro|pro|evo)\b",
        folded,
    )
    if match:
        return f"{match.group(1)} {match.group(2)}"
    match = re.search(r"\b(rtx|gtx)\s*(\d{4})\s*(ti|super)?\b", folded)
    if match:
        return " ".join(part for part in match.groups() if part)
    match = _IPHONE_MODEL_RE.search(folded)
    if match:
        base = match.group(1)
        suffix = (match.group(2) or "").strip()
        return f"iphone {base}" + (f" {suffix}" if suffix else "")
    match = re.search(r"\bideapad\s*slim\s*(\d+i?)\b", folded)
    if match:
        return f"ideapad slim {match.group(1)}"
    # Consoles: expand compacted identity (playstation5digital) for SERP.
    # Omit "slim" from the primary phrase — Shopping China (and similar) treat
    # "slim" as a hard token and return [] / wrong Pro SKUs when combined with
    # brand+storage. Slim remains optional evidence, not a SERP requirement.
    model_fold = fold_text(model or "")
    if "playstation5" in model_fold or re.search(r"\b(?:playstation|ps)\s*5\b", folded):
        parts = ["playstation 5"]
        blob = f"{model_fold} {folded}"
        edition = _console_edition_signature(blob) or _console_edition_signature(folded)
        if edition:
            parts.append(edition)
        return " ".join(parts)
    if model and not looks_like_mpn(model) and " " in (title or ""):
        # Last resort: avoid emitting compacted tokens like ``990evoplus``.
        return None
    return None


def rank_candidates_for_query(
    candidates: list[Any],
    query: str,
) -> list[Any]:
    """Stable-reorder SERP hits so query-relevant titles/MPNs surface first.

    Does not drop candidates — only improves retrieval when the retailer ranks
    sibling SKUs above the exact PN/series match.

    Ranking uses title + URL **path** only. Amazon SERP links embed the full
    ``keywords=`` query in the query-string, which would otherwise make every
    card look like an exact compact match.
    """
    from urllib.parse import urlsplit

    q_fold = fold_text(query)
    q_tokens = {tok for tok in re.findall(r"[a-z0-9]+", q_fold) if len(tok) >= 2}
    q_compact = re.sub(r"[^a-z0-9]+", "", q_fold)
    # Tokens that often distinguish variants (colors, storage) — boost title hits.
    variantish = {
        tok
        for tok in q_tokens
        if tok in COLOR_CANONICAL
        or tok in COLOR_CANONICAL.values()
        or re.fullmatch(r"\d+gb", tok)
        or re.fullmatch(r"\d+tb", tok)
    }

    def sort_key(candidate: Any) -> tuple[int, int, int, int]:
        title = fold_text(getattr(candidate, "title", None) or "")
        raw_url = getattr(candidate, "url", None) or ""
        path = urlsplit(raw_url).path or ""
        path_fold = fold_text(path)
        title_compact = re.sub(r"[^a-z0-9]+", "", title)
        path_compact = re.sub(r"[^a-z0-9]+", "", path_fold)
        exact = (
            1
            if q_compact
            and len(q_compact) >= 8
            and (q_compact in title_compact or q_compact in path_compact)
            else 0
        )
        title_tokens_set = set(re.findall(r"[a-z0-9]+", title))
        token_hits = len(q_tokens & title_tokens_set)
        variant_hits = len(variantish & title_tokens_set)
        return (exact, variant_hits, token_hits, min(len(title), 200))

    return sorted(candidates, key=sort_key, reverse=True)


def looks_like_mpn(token: str | None) -> bool:
    """True when a normalized model string looks like an opaque manufacturer PN."""
    if not token or len(token) < 8:
        return False
    if _model_has_family(token):
        return False
    if re.fullmatch(r"mz[a-z0-9]{6,}", token):
        return True
    if re.fullmatch(r"cfi\d{4}[a-z]?", token):
        return True
    # Mixed letter+digit opaque codes without commercial family markers.
    has_letter = any(ch.isalpha() for ch in token)
    has_digit = any(ch.isdigit() for ch in token)
    return has_letter and has_digit and not token.startswith(("iphone", "rtx", "gtx"))


def _gpu_signature(text: str | None) -> str | None:
    folded = fold_text(text or "")
    match = re.search(r"\b(rtx|gtx)\s*(\d{4})\s*(ti|super)?\b", folded)
    if not match:
        return None
    suffix = match.group(3) or ""
    return f"{match.group(1)}{match.group(2)}{suffix}"


def _gpu_edition_signature(text: str | None) -> str | None:
    """Commercial cooler/edition line for discrete GPUs (missing ≠ conflict).

    Category-aware title parsing keeps cooler lines (Shadow 3X, Dual OC) out of
    the chip model. Missing edition is unknown, not a mismatch.
    """
    if not text:
        return None
    parsed = parse_title_identity(text, category="gpu")
    if parsed.variant_key:
        return parsed.variant_key
    return canonical_variant_key(parsed.variant) if parsed.variant else None


def _gpu_vram_from_text(text: str | None) -> str | None:
    folded = fold_text(text or "")
    if not folded or not _gpu_signature(folded):
        return None
    match = re.search(r"\b(8|10|12|16|20|24)\s*g(?:b|ddr)?\b", folded)
    if not match:
        return None
    return f"{match.group(1)}gb"


def _memory_type_signature(text: str | None) -> str | None:
    match = re.search(r"\bgddr\s*([567])\b", fold_text(text or ""))
    if not match:
        return None
    return f"gddr{match.group(1)}"


def _ssd_signature(text: str | None) -> str | None:
    folded = fold_text(text or "")
    match = re.search(
        r"\b([89]\d0)\s*(evo\s*plus|evo\s*pro|pro|evo)\b",
        folded,
    )
    if not match:
        return None
    return normalize_model(f"{match.group(1)} {match.group(2)}")


def _phone_signature(text: str | None) -> str | None:
    folded = fold_text(text or "")
    match = _IPHONE_MODEL_RE.search(folded)
    if match:
        suffix = (match.group(2) or "").replace(" ", "")
        return normalize_model(f"iphone {match.group(1)}{suffix}")
    match = re.search(
        r"\bgalaxy\s*s(\d{1,2})(?:\s*(ultra|plus|\+|fe))?\b",
        folded,
    )
    if match:
        suffix = (match.group(2) or "").replace("+", "plus")
        return normalize_model(f"galaxys{match.group(1)}{suffix}")
    return None


def _console_edition_signature(text: str | None) -> str | None:
    """Return ``digital`` / ``disc`` when the listing explicitly states edition.

    Missing edition is ``None`` (unknown) — never invent from marketing noise.
    """
    folded = fold_text(text or "")
    if not folded:
        return None
    # Require console family context so "digital" camera kits don't fire.
    if not re.search(r"\b(?:playstation|ps)\s*5\b|\bps5\b|\bcfi-?\d", folded):
        return None
    if re.search(
        r"\bdigital(?:\s+edition)?\b|\bedicao\s+digital\b|\bedici[oó]n\s+digital\b",
        folded,
    ):
        return "digital"
    if re.search(
        r"\bdisc(?:\s+version|\s+edition)?\b|\bblu-?ray\b|\boptical\b|"
        r"\bedicao\s+(?:fisica|disco)\b",
        folded,
    ):
        return "disc"
    return None


def _controller_count_signature(text: str | None) -> int | None:
    """Explicit controller quantity when stated; ``None`` means unknown."""
    folded = fold_text(text or "")
    if not folded:
        return None
    match = re.search(
        r"\b(\d+)\s*(?:controles?|controllers?|dualsense)\b",
        folded,
    )
    if match:
        count = int(match.group(1))
        if 1 <= count <= 4:
            return count
    if re.search(r"\b(?:dois|two)\s+controles?\b|\bdualsense\s*x\s*2\b", folded):
        return 2
    if re.search(r"\b(?:um|one|1)\s+controle\b", folded):
        return 1
    return None


def _ddr_signature(text: str | None) -> str | None:
    match = re.search(r"\bddr\s*([45])\b", fold_text(text or ""))
    if not match:
        return None
    return f"ddr{match.group(1)}"


def _edition_token(identity: ProductIdentity) -> str | None:
    blob = identity.title
    from_text = _gpu_edition_signature(blob)
    raw = from_text or identity.variant_attrs.get("edition")
    if not raw:
        return None
    return normalize_variant_value("edition", str(raw)) or None


def _edition_search_phrase(identity: ProductIdentity) -> str | None:
    """Spaced commercial edition for SERP (``shadow 3x oc``), not compacted token."""
    parsed = parse_title_identity(identity.title, category="gpu")
    if parsed.variant:
        return re.sub(r"\s+", " ", parsed.variant).strip().casefold()
    raw = identity.variant_attrs.get("edition")
    if not raw:
        return None
    token = fold_text(str(raw))
    token = re.sub(r"(\d+)x", r" \1x ", token)
    token = re.sub(r"oc$", " oc", token)
    token = re.sub(r"([a-z])(\d)", r"\1 \2", token)
    return re.sub(r"\s+", " ", token).strip() or None


def _identity_blob(model: str | None, title: str | None) -> str:
    return f"{model or ''} {title or ''}".strip()


def critical_identity_conflict(
    reference: ProductIdentity,
    candidate: ProductIdentity,
) -> str | None:
    """Return a blocker code when critical category attributes diverge.

    Precision-first: incompatible GPU suffix, phone trim, SSD series, DDR
    generation, console edition (digital≠disc), explicit controller counts,
    or product storage capacity must not be compensated by title similarity.

    Missing attributes are **not** conflicts — only explicit disagreements.
    """
    checks: tuple[tuple[str, str | None, str | None], ...] = (
        (
            "gpu",
            _gpu_signature(_identity_blob(reference.model, reference.title)),
            _gpu_signature(_identity_blob(candidate.model, candidate.title)),
        ),
        (
            "gpu_edition",
            _edition_token(reference),
            _edition_token(candidate),
        ),
        (
            "ssd",
            _ssd_signature(_identity_blob(reference.model, reference.title)),
            _ssd_signature(_identity_blob(candidate.model, candidate.title)),
        ),
        (
            "phone",
            _phone_signature(_identity_blob(reference.model, reference.title)),
            _phone_signature(_identity_blob(candidate.model, candidate.title)),
        ),
        (
            "ddr",
            _ddr_signature(_identity_blob(reference.model, reference.title)),
            _ddr_signature(_identity_blob(candidate.model, candidate.title)),
        ),
        (
            "console_edition",
            _console_edition_signature(
                _identity_blob(reference.model, reference.title)
            ),
            _console_edition_signature(
                _identity_blob(candidate.model, candidate.title)
            ),
        ),
    )
    for name, left, right in checks:
        if left and right and left != right:
            return f"{name}_mismatch:{left}!={right}"

    ref_controllers = _controller_count_signature(reference.title)
    cand_controllers = _controller_count_signature(candidate.title)
    if (
        ref_controllers is not None
        and cand_controllers is not None
        and ref_controllers != cand_controllers
    ):
        return f"controller_count_mismatch:{ref_controllers}!={cand_controllers}"

    ref_vram = reference.variant_attrs.get("vram") or _gpu_vram_from_text(
        _identity_blob(reference.model, reference.title)
    )
    cand_vram = candidate.variant_attrs.get("vram") or _gpu_vram_from_text(
        _identity_blob(candidate.model, candidate.title)
    )
    if ref_vram and cand_vram:
        left = normalize_variant_value("vram", str(ref_vram))
        right = normalize_variant_value("vram", str(cand_vram))
        if left and right and left != right:
            return f"vram_mismatch:{left}!={right}"

    ref_storage = reference.variant_attrs.get("storage") or reference.variant_attrs.get(
        "capacity"
    )
    cand_storage = candidate.variant_attrs.get(
        "storage"
    ) or candidate.variant_attrs.get("capacity")
    if not ref_storage:
        ref_storage = _storage_like_from_title(reference.title)
    if not cand_storage:
        cand_storage = _storage_like_from_title(candidate.title)
    if ref_storage and cand_storage:
        left = normalize_variant_value("storage", ref_storage)
        right = normalize_variant_value("storage", cand_storage)
        left_gb = _capacity_gb(left)
        right_gb = _capacity_gb(right)
        if (
            left_gb is not None
            and right_gb is not None
            and left_gb >= _STORAGE_LIKE_MIN_GB
            and right_gb >= _STORAGE_LIKE_MIN_GB
            and left_gb != right_gb
        ):
            return f"storage_mismatch:{left}!={right}"
    return None


def models_compatible(
    left: str | None,
    right: str | None,
    *,
    left_title: str | None = None,
    right_title: str | None = None,
) -> bool:
    """True when model tokens refer to the same product line (not opaque SKUs)."""
    left_blob = _identity_blob(left, left_title)
    right_blob = _identity_blob(right, right_title)
    left_mpns = {norm for norm, _ in extract_all_mpn_forms(left, left_title)}
    right_mpns = {norm for norm, _ in extract_all_mpn_forms(right, right_title)}
    left_mpn = next(iter(sorted(left_mpns)), None)
    right_mpn = next(iter(sorted(right_mpns)), None)
    if left_mpns and right_mpns and left_mpns & right_mpns:
        return True

    left_ssd = _ssd_signature(left_blob)
    right_ssd = _ssd_signature(right_blob)
    if left_ssd and right_ssd:
        return left_ssd == right_ssd

    left_gpu = _gpu_signature(left_blob)
    right_gpu = _gpu_signature(right_blob)
    if left_gpu and right_gpu:
        return left_gpu == right_gpu

    left_phone = _phone_signature(left_blob)
    right_phone = _phone_signature(right_blob)
    if left_phone and right_phone:
        return left_phone == right_phone

    if not left or not right:
        # One side only has a commercial series inferred from the other title.
        if left_ssd and left_ssd == infer_model_from_title(right_title):
            return True
        if right_ssd and right_ssd == infer_model_from_title(left_title):
            return True
        return False

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

    # Opaque MPN on one side + commercial series on the other: accept when the
    # same MPN appears in the commercial side's title and series signatures match.
    right_compact = normalize_model(right_title or "") or ""
    left_compact = normalize_model(left_title or "") or ""
    if looks_like_mpn(left) and right_ssd and left_mpn and left_mpn in right_compact:
        return True
    if looks_like_mpn(right) and left_ssd and right_mpn and right_mpn in left_compact:
        return True

    a, b = compact_model(left), compact_model(right)
    if a == b:
        return True
    # Naming drift: IdeaPad Slim 3 vs Slim 3i
    if a + "i" == b or b + "i" == a:
        return True

    # PlayStation 5 family: edition/slim suffixes are optional when not conflicting.
    # Explicit digital≠disc is handled by critical_identity_conflict.
    if ("playstation5" in a or a.startswith("ps5")) and (
        "playstation5" in b or b.startswith("ps5")
    ):
        left_ed = _console_edition_signature(left_blob)
        right_ed = _console_edition_signature(right_blob)
        if left_ed and right_ed and left_ed != right_ed:
            return False
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
    # Critical suffixes must not be soft-matched (Ti / Super / Pro / Max / Plus…).
    if rest in {"ti", "super", "oc", "pro", "plus", "max", "ultra"}:
        return False
    # Console edition / slim as optional soft suffixes (conflict gated elsewhere).
    if rest in {"digital", "disc", "bluray", "slim", "ps5"}:
        return True
    return rest in {"i", "air"}


def infer_model_from_title(title: str | None) -> str | None:
    """Best-effort commercial model token from title when structured model is weak."""
    folded = fold_text(title or "")
    if not folded:
        return None
    phone = _phone_signature(folded)
    if phone:
        # Re-space for display-ish tokens used only as identity model keys.
        return phone
    match = re.search(r"\bideapad\s*slim\s*(\d+i?)\b", folded)
    if match:
        return normalize_model(f"ideapad slim {match.group(1)}")
    ssd = _ssd_signature(folded)
    if ssd:
        return ssd
    gpu = _gpu_signature(folded)
    if gpu:
        return gpu
    match = re.search(
        r"\b(?:playstation|ps)\s*5(?:\s*(slim))?(?:\s*(digital|disc|bluray))?\b",
        folded,
    )
    if match:
        parts = ["playstation5"]
        if match.group(1):
            parts.append(match.group(1))
        if match.group(2):
            parts.append(match.group(2))
        else:
            # Edition may appear away from the "PS5" token (e.g. CFI code in between).
            edition = _console_edition_signature(folded)
            if edition:
                parts.append(edition)
        if re.search(r"\bslim\b", folded) and "slim" not in parts:
            parts.insert(1, "slim")
        return normalize_model(" ".join(parts))
    if re.search(r"\bps5\b", folded):
        parts = ["playstation5"]
        if re.search(r"\bslim\b", folded):
            parts.append("slim")
        edition = _console_edition_signature(folded)
        if edition:
            parts.append(edition)
        return normalize_model(" ".join(parts))
    return None


def resolve_model(raw_model: str | None, title: str | None) -> str | None:
    """Prefer commercial/family model strings; keep MPN only when nothing better."""
    blob = _identity_blob(raw_model, title)
    # Discrete GPUs: chip identity (rtx5070 / rtx5070ti) is the model token;
    # cooler lines (Shadow 3X) live in variant_attrs.edition, not model.
    gpu = _gpu_signature(blob)
    if gpu:
        return gpu

    structured = normalize_model(raw_model)
    inferred = infer_model_from_title(title)
    if structured and _model_has_family(structured) and not looks_like_mpn(structured):
        # Generic "PlayStation 5" / "PS5" in structured fields often omits Slim /
        # Digital / Disc. Prefer the title-inferred token when it only *adds*
        # edition/revision detail (never when it invents a different family).
        if inferred:
            base = compact_model(structured)
            rich = compact_model(inferred)
            if rich.startswith(base) and len(rich) > len(base):
                return inferred
        return structured
    if inferred:
        return inferred
    if structured and not looks_like_mpn(structured):
        return structured
    if structured and looks_like_mpn(structured) and inferred:
        return inferred
    return structured or inferred


def console_soft_model_title_exempt(
    reference: ProductIdentity,
    candidate: ProductIdentity,
) -> bool:
    """Title similarity is complementary for consoles — not a soft-model gate.

    Sparse listings (Shopping China) vs marketing-heavy titles (KaBuM / Amazon)
    often score below ``SOFT_MODEL_TITLE_MIN`` even when edition + storage agree.
    Explicit digital≠disc / controller / storage conflicts stay in
    ``critical_identity_conflict``.
    """
    left = compact_model(reference.model or "")
    right = compact_model(candidate.model or "")
    if not left or not right:
        return False
    if not (
        ("playstation5" in left or left.startswith("ps5"))
        and ("playstation5" in right or right.startswith("ps5"))
    ):
        return False
    if not models_compatible(
        reference.model,
        candidate.model,
        left_title=reference.title,
        right_title=candidate.title,
    ):
        return False
    return critical_identity_conflict(reference, candidate) is None


def gpu_soft_model_title_exempt(
    reference: ProductIdentity,
    candidate: ProductIdentity,
) -> bool:
    """Title noise (DLSS / MHz / bus) must not veto GPU chip+edition identity."""
    left = _gpu_signature(_identity_blob(reference.model, reference.title))
    right = _gpu_signature(_identity_blob(candidate.model, candidate.title))
    if not left or not right or left != right:
        return False
    return critical_identity_conflict(reference, candidate) is None


def _canonical_color(text: str) -> str:
    text = re.sub(r"[-_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
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
    if key in {"storage", "capacity", "ram", "size", "vram"}:
        # "256 gb" / "256GB" / "12G" → "256gb" / "12gb"
        compacted = re.sub(r"\s+", "", text)
        match = re.fullmatch(r"(\d+)(gb|tb|mb|g|mm|cm|in|\"|')?", compacted)
        if match:
            unit = match.group(2) or ""
            if unit == "g":
                unit = "gb"
            return f"{match.group(1)}{unit}"
        return compacted
    if key == "edition":
        return canonical_variant_key(text) or re.sub(r"[^a-z0-9]+", "", text)
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


def _color_label_from_title(title: str | None) -> str | None:
    """Pick the longest known color label mentioned in the title."""
    folded = re.sub(r"[-_]+", " ", fold_text(title or ""))
    folded = re.sub(r"\s+", " ", folded).strip()
    if not folded:
        return None
    best: str | None = None
    for label in COLOR_CANONICAL:
        if re.search(rf"\b{re.escape(label)}\b", folded):
            if best is None or len(label) > len(best):
                best = label
    return best


def canonicalize_variant_key(key: str, value: str) -> str:
    """Map locale attribute names onto VARIANT_GATE_KEYS.

    ``tamanho`` / ``size`` values that look like device storage (≥128GB) are
    promoted to ``storage`` so phone/SSD capacities participate in the gate.
    """
    key_n = fold_text(key).replace(" ", "_")
    mapped = _VARIANT_KEY_ALIASES.get(key_n, key_n)
    if mapped == "size":
        norm = normalize_variant_value("storage", value)
        gb = _capacity_gb(norm)
        if gb is not None and gb >= _STORAGE_LIKE_MIN_GB:
            return "storage"
    return mapped


def parse_variant_attributes(
    variant: str | None,
    *,
    specifications: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Parse `color: …; storage: …` variant strings plus optional specs."""
    attrs: dict[str, str] = {}

    def _store(raw_key: str, raw_value: str) -> None:
        text = str(raw_value).strip()
        if not text or text.lower() == "none":
            return
        key_n = canonicalize_variant_key(raw_key, text)
        if key_n not in VARIANT_GATE_KEYS:
            return
        if key_n in attrs:
            return
        if key_n in {"storage", "capacity", "ram", "size"}:
            attrs[key_n] = normalize_variant_value(key_n, text)
        else:
            folded = fold_text(text)
            folded = re.sub(r"\s+", " ", folded).strip()
            if folded:
                attrs[key_n] = folded

    if variant:
        for part in variant.split(";"):
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            _store(key, value)
    for source in (specifications or {}, extra or {}):
        for key, value in source.items():
            if value is None:
                continue
            _store(str(key), str(value))
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
    # Compact capacity units so "128 GB" and "128GB" share a token.
    folded = re.sub(r"\b(\d+)\s*(gb|tb|mb)\b", r"\1\2", folded)

    # Keep manufacturer PNs as a single token before punctuation stripping.
    def _compact_mpn(match: re.Match[str]) -> str:
        return normalize_mpn(match.group(0)) or match.group(0)

    for pattern in _MPN_PATTERNS:
        folded = pattern.sub(_compact_mpn, folded)
    folded = re.sub(r"[^a-z0-9\s]+", " ", folded)
    tokens = [t for t in folded.split() if t and t not in TITLE_STOPWORDS]
    # Map single-token color synonyms so PT/EN titles overlap.
    tokens = [COLOR_CANONICAL.get(token, token) for token in tokens]
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


def looks_like_bundle(title: str | None, *, reference_title: str | None) -> bool:
    """True when candidate adds extra merchandise absent from the reference.

    Pack-in games (Astro's Playroom) and marketing tokens (Bluetooth, 8K,
    DualSense singular) are not treated as bundles. Explicit extra games
    (Fortnite, GT7, …) or kit/watch merchandise are.
    """
    cand = fold_text(title or "")
    ref = fold_text(reference_title or "")
    if not cand:
        return False
    cand_bundle = any(marker in cand for marker in _BUNDLE_MARKERS)
    ref_bundle = any(marker in ref for marker in _BUNDLE_MARKERS)
    return cand_bundle and not ref_bundle


def looks_like_used_condition(title: str | None) -> bool:
    """True when the listing title indicates refurbished / used / CPO stock."""
    folded = fold_text(title or "")
    if not folded:
        return False
    for token in _CONDITION_TOKENS:
        if " " in token or "-" in token:
            if token in folded:
                return True
        elif re.search(rf"\b{re.escape(token)}\b", folded):
            return True
    return False


def condition_conflict(
    reference_title: str | None,
    candidate_title: str | None,
) -> str | None:
    """Reject used/refurbished candidates when the reference is a new listing."""
    if looks_like_used_condition(candidate_title) and not looks_like_used_condition(
        reference_title
    ):
        return "condition_mismatch:new!=used"
    return None


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
    mpn: str | None = None
    mpn_display: str | None = None
    mpn_aliases: frozenset[str] = field(default_factory=frozenset)

    @property
    def variant_key(self) -> str | None:
        return variant_key(self.variant_attrs)


def identity_from_price_item(item: ProductPriceItem) -> ProductIdentity:
    meta = item.metadata if isinstance(item.metadata, dict) else {}
    raw_specs = meta.get("specifications")
    specs: dict[str, Any] = raw_specs if isinstance(raw_specs, dict) else {}
    extra: dict[str, Any] = {}
    for key in ("color", "storage", "size", "capacity", "ram", "vram", "edition"):
        value = meta.get(key)
        if (
            value is not None
            and str(value).strip()
            and str(value).strip().lower() != "none"
        ):
            extra[key] = value
    # Bare Magalu-style variant ("Preto") → treat as color when no key:value form.
    variant = item.variant
    if variant and ":" not in variant:
        gpu_blob = _identity_blob(item.model, item.title)
        if extract_gpu_chip(gpu_blob) is not None or extract_gpu_chip(variant):
            extra.setdefault("edition", variant)
        elif "color" not in extra:
            extra["color"] = variant
    # Pull storage tokens from title when structured variant lacks them.
    attrs = parse_variant_attributes(
        variant if variant and ":" in variant else None,
        specifications=specs,
        extra=extra,
    )
    refine_storage_attrs(attrs, item.title)
    if "color" not in attrs:
        title_color = _color_label_from_title(item.title)
        if title_color:
            attrs["color"] = title_color

    blob = _identity_blob(item.model, item.title)
    # GPU VRAM is often mis-tagged as RAM by generic parsers — promote when GPU.
    if _gpu_signature(blob):
        if "vram" not in attrs:
            vram = (
                attrs.pop("ram", None)
                if attrs.get("ram")
                else _gpu_vram_from_text(blob)
            )
            if vram:
                attrs["vram"] = normalize_variant_value("vram", str(vram))
        elif "ram" in attrs and normalize_variant_value(
            "ram", str(attrs["ram"])
        ) == normalize_variant_value("vram", str(attrs["vram"])):
            attrs.pop("ram", None)
        if "edition" not in attrs:
            edition = _gpu_edition_signature(item.title) or _gpu_edition_signature(
                " ".join(str(v) for v in specs.values() if v)
            )
            if edition:
                attrs["edition"] = normalize_variant_value("edition", edition)
        memory_type = _memory_type_signature(blob) or _memory_type_signature(
            " ".join(str(v) for v in specs.values() if v)
        )
        if memory_type and "memory_type" not in attrs:
            attrs["memory_type"] = memory_type

    model = resolve_model(item.model, item.title)
    # Spec REFERÊNCIA / manufacturer codes feed MPN extraction alongside sku/title.
    spec_mpn_bits = [
        str(specs[key])
        for key in specs
        if fold_text(str(key))
        in {
            "referencia",
            "reference",
            "mpn",
            "part number",
            "codigo do fabricante",
            "manufacturer code",
        }
    ]
    mpn_forms = extract_all_mpn_forms(item.model, item.sku, item.title, *spec_mpn_bits)
    mpn = mpn_forms[0][0] if mpn_forms else None
    mpn_display = mpn_forms[0][1] if mpn_forms else None
    mpn_aliases = frozenset(norm for norm, _disp in mpn_forms)
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
        mpn=mpn,
        mpn_display=mpn_display,
        mpn_aliases=mpn_aliases,
    )


# Prefer color/storage queries before the brand+series-only drop so Amazon
# SERPs that promote sibling colors still surface the right card early.
def build_search_queries(identity: ProductIdentity) -> list[str]:
    """Ordered SERP queries: GTIN → display MPN → spaced series → title tokens.

    Compacted identity tokens (``990evoplus``, ``mzv9s1t0bam``) are weak on
    Amazon-like SERPs; prefer hyphenated PNs and human-spaced model phrases.
    Color queries emit locale synonyms (``preto`` / ``black``) without dropping
    critical storage/model attributes.

    For discrete GPUs, prefer progressive commercial queries
    (brand + chip + edition + VRAM) before noisy SEO title prefixes.
    """
    queries: list[str] = []

    def add(raw: str | None) -> None:
        text = (raw or "").strip()
        if text and text not in queries:
            queries.append(text)

    add(identity.gtin)

    # Collect manufacturer PN displays for later (after category-specific ladders).
    alias_displays: list[str] = []
    if identity.mpn_display:
        alias_displays.append(identity.mpn_display)
    for _norm, display in extract_all_mpn_forms(
        identity.mpn_display,
        identity.mpn,
        identity.model,
        identity.title,
        *identity.mpn_aliases,
    ):
        if display not in alias_displays:
            alias_displays.append(display)

    series = model_search_phrase(model=identity.model, title=identity.title)
    storage = identity.variant_attrs.get("storage") or identity.variant_attrs.get(
        "capacity"
    )
    vram = identity.variant_attrs.get("vram")
    color = identity.variant_attrs.get("color")
    edition = _edition_search_phrase(identity)
    memory_type = identity.variant_attrs.get("memory_type") or _memory_type_signature(
        _identity_blob(identity.model, identity.title)
    )
    gpu = _gpu_signature(_identity_blob(identity.model, identity.title))
    console_edition = _console_edition_signature(
        _identity_blob(identity.model, identity.title)
    )
    series_fold = fold_text(series or "")
    if console_edition and console_edition in series_fold:
        console_edition = None

    # --- GPU progressive ladder (discriminating attrs first, noise last) ---
    # Prefer commercial identity before bare board/marketing PNs: BR SERPs often
    # surface marketplace siblings for opaque codes while Shadow/VRAM queries
    # rediscover the exact cooler line.
    if gpu:
        spaced_gpu = re.sub(r"(rtx|gtx)(\d{4})(ti|super)?", r"\1 \2 \3", gpu).strip()
        spaced_gpu = re.sub(r"\s+", " ", spaced_gpu).strip()
        capacity = vram or storage
        ladder: list[list[str]] = []
        full = [
            p for p in (identity.brand, spaced_gpu, edition, capacity, memory_type) if p
        ]
        ladder.append(full)
        ladder.append([p for p in (identity.brand, spaced_gpu, edition, capacity) if p])
        ladder.append([p for p in (identity.brand, spaced_gpu, edition) if p])
        ladder.append([p for p in (identity.brand, spaced_gpu, capacity) if p])
        ladder.append([p for p in (identity.brand, spaced_gpu) if p])
        if edition and capacity:
            ladder.append([p for p in (spaced_gpu, edition, capacity) if p])
        for parts in ladder:
            if parts:
                add(" ".join(parts))
        for display in alias_displays:
            add(display)
            if identity.brand:
                add(f"{identity.brand} {display}")
        if identity.mpn:
            add(identity.mpn)
            if identity.brand:
                add(f"{identity.brand} {identity.mpn}")
        return queries

    # Bare manufacturer PN ranks best on Amazon BR for exact SKU recovery
    # (non-GPU categories).
    for display in alias_displays:
        add(display)
        if identity.brand:
            add(f"{identity.brand} {display}")

    # Colorless series+storage first: locale color tokens (branco/black) often
    # miss on foreign SERPs (Shopping China) even when the SKU is present.
    series_parts = [part for part in (identity.brand, series) if part]
    capacity = storage or vram
    if capacity:
        series_parts.append(capacity)
    if console_edition:
        series_parts.append(console_edition)
    if edition and not gpu:
        series_parts.append(str(edition))
    add(" ".join(series_parts) if series_parts else None)

    # Brandless series+storage early — some catalogs (Shopping China) rank
    # better without the brand token and empty out on brand+slim combos.
    if series and capacity:
        add(f"{series} {capacity}")
    elif series and console_edition:
        add(f"{series} {console_edition}")

    color_labels: list[str] = []
    if color:
        color_labels.append(color)
        canon = normalize_variant_value("color", color)
        for synonym in _COLOR_SEARCH_SYNONYMS.get(canon, (canon,)):
            if synonym not in color_labels:
                color_labels.append(synonym)

    for color_label in color_labels:
        colored = [part for part in (identity.brand, series) if part]
        if capacity:
            colored.append(capacity)
        if console_edition:
            colored.append(console_edition)
        colored.append(color_label)
        add(" ".join(colored))

    # Progressive drop: keep critical model+storage without brand/color.
    if series and capacity:
        add(f"{series} {capacity}")
    if series and console_edition:
        add(f"{series} {console_edition}")
    if identity.brand and series:
        add(f"{identity.brand} {series}")

    # Compacted fallbacks for catalogs that index alnum-only PNs.
    if identity.mpn:
        add(identity.mpn)
        if identity.brand:
            add(f"{identity.brand} {identity.mpn}")

    tokens = identity.title_normalized.split()
    if tokens:
        # Drop marketing/noise tokens before taking a title window.
        noise = {
            "placa",
            "video",
            "geforce",
            "nvidia",
            "amd",
            "radeon",
            "ray",
            "tracing",
            "dlss",
            "fp4",
            "mhz",
            "bit",
            "bits",
            "pcie",
            "pci",
            "express",
        }
        filtered = [tok for tok in tokens if tok not in noise]
        window = filtered[:8] if filtered else tokens[:8]
        add(" ".join(window))
    return queries
