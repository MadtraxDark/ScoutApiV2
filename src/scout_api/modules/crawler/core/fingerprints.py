from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "gbraid",
    "wbraid",
    "gad_source",
    "gad_campaignid",
    "ref",
    "ref_",
    "source",
    "from",
    "sp_atk",
    "utm_campaign",
    "utm_medium",
    "utm_source",
    "utm_term",
    "utm_content",
    "xptdk",
}

# Marketing / affiliate prefixes (Mercado Livre Google Shopping, etc.)
TRACKING_PREFIXES = ("matt_", "cq_", "gad_")


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query):
        lowered = key.lower()
        if lowered in TRACKING_KEYS:
            continue
        if any(lowered.startswith(prefix) for prefix in TRACKING_PREFIXES):
            continue
        kept.append((key, value))
    query = urlencode(kept)
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            query,
            "",
        )
    )


def request_fingerprint(
    store: str, url: str, product_id: str, variant: str | None = None
) -> str:
    value = "|".join((store, canonicalize_url(url), product_id, variant or ""))
    return sha256(value.encode()).hexdigest()
