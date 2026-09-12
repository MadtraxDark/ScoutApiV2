from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "ref",
    "ref_",
    "source",
    "sp_atk",
    "utm_campaign",
    "utm_medium",
    "utm_source",
    "utm_term",
    "xptdk",
}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_KEYS]
    )
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
