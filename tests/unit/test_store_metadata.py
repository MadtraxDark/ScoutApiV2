import io
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

from scout_api.modules.crawler.stores import STORE_CONFIGS
from scout_api.modules.images.optimizer import AvifOptimizer
from scout_api.modules.matching.router import _store_logo_url
from scout_api.modules.matching.schemas import StoreMetadataUpdateRequest
from scout_api.modules.matching.store_metadata_service import (
    InvalidStoreLogoError,
    StoreMetadataService,
    StoreNotFoundError,
    validate_store_logo,
    validate_store_logo_upload,
)


def test_store_logo_asset_url_changes_when_optimized_variant_is_ready() -> None:
    metadata = SimpleNamespace(
        logo_mime_type="image/png",
        logo_svg=None,
        logo_version="version-b",
        logo_optimized_file_id=None,
    )

    original_url = _store_logo_url("kabum", metadata)
    metadata.logo_optimized_file_id = "avif-file-id"
    optimized_url = _store_logo_url("kabum", metadata)

    assert original_url == "/stores/kabum/logo?v=version-b-original"
    assert optimized_url == "/stores/kabum/logo?v=version-b-avif"
    assert optimized_url != original_url


class Repository:
    def __init__(self) -> None:
        self.saved: tuple[str, str | None] | None = None

    def get_all(self) -> dict[str, object]:
        return {}

    def save(self, key: str, name: str, logo_svg: str | None) -> SimpleNamespace:
        self.saved = (name, logo_svg)
        return SimpleNamespace(store_key=key, display_name=name, logo_svg=logo_svg)


def test_update_registered_store_saves_only_admin_metadata() -> None:
    repository = Repository()
    result = StoreMetadataService(repository).update(
        "kabum", "  KaBuM Tech  ", '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    )
    assert repository.saved == (
        "KaBuM Tech",
        '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
    )
    assert result.store_key == "kabum"


def test_update_rejects_unregistered_store() -> None:
    with pytest.raises(StoreNotFoundError):
        StoreMetadataService(Repository()).update("arbitrary-site", "Site", None)


@pytest.mark.parametrize(
    "svg",
    [
        "<svg><script>alert(1)</script></svg>",
        '<svg><image href="https://attacker.example/image.svg"/></svg>',
        '<svg onload="alert(1)"></svg>',
        "<!DOCTYPE svg><svg></svg>",
    ],
)
def test_rejects_unsafe_or_oversized_svg(svg: str) -> None:
    with pytest.raises(InvalidStoreLogoError):
        validate_store_logo(svg)


def test_rejects_non_svg_content() -> None:
    with pytest.raises(InvalidStoreLogoError):
        validate_store_logo("not an svg")


def test_rejects_oversized_svg() -> None:
    with pytest.raises(InvalidStoreLogoError):
        validate_store_logo("<svg>" + ("a" * (2 * 1_048_576)) + "</svg>")


def _raster_bytes(fmt: str, *, alpha: bool = False) -> bytes:
    image = Image.new(
        "RGBA" if alpha else "RGB", (12, 8), (20, 40, 60, 90) if alpha else (20, 40, 60)
    )
    output = io.BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


@pytest.mark.parametrize(
    ("fmt", "extension", "mime"),
    [
        ("PNG", "png", "image/png"),
        ("WEBP", "webp", "image/webp"),
        ("JPEG", "jpg", "image/jpeg"),
        ("JPEG", "jpeg", "image/jpeg"),
    ],
)
def test_accepts_raster_logo_when_signature_mime_and_extension_match(
    fmt: str, extension: str, mime: str
) -> None:
    upload = validate_store_logo_upload(_raster_bytes(fmt), f"logo.{extension}", mime)
    assert upload.mime_type == mime
    assert not upload.is_svg


def test_rejects_renamed_raster_and_mime_mismatch() -> None:
    data = _raster_bytes("PNG")
    with pytest.raises(InvalidStoreLogoError):
        validate_store_logo_upload(data, "logo.jpg", "image/jpeg")
    with pytest.raises(InvalidStoreLogoError):
        validate_store_logo_upload(data, "logo.png", "image/jpeg")


def test_accepts_self_contained_svg_upload() -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
    upload = validate_store_logo_upload(svg, "logo.svg", "image/svg+xml")
    assert upload.is_svg
    assert upload.mime_type == "image/svg+xml"


def test_accepts_avif_without_reconverting_and_preserves_transparency() -> None:
    source = _raster_bytes("PNG", alpha=True)
    try:
        optimized = AvifOptimizer().convert(source)
        avif = _raster_bytes("AVIF", alpha=True)
    except (OSError, ValueError) as exc:
        pytest.skip(f"AVIF encoder/decoder unavailable: {exc}")
    uploaded = validate_store_logo_upload(avif, "logo.avif", "image/avif")
    assert uploaded.mime_type == "image/avif"
    with Image.open(io.BytesIO(optimized.data)) as image:
        assert "A" in image.getbands()
        assert image.size == (12, 8)


def test_update_request_rejects_structural_fields() -> None:
    with pytest.raises(ValidationError):
        StoreMetadataUpdateRequest(
            display_name="KaBuM Nova",
            domains=["arbitrary.example"],
            country="PY",
            currency="EUR",
        )


def test_store_market_pairs_are_declared_per_integration() -> None:
    assert STORE_CONFIGS["visaovip"].market_pairs == (("PY", "USD"),)
    assert ("PY", "EUR") not in STORE_CONFIGS["visaovip"].market_pairs
    assert STORE_CONFIGS["nissei"].market_pairs == (("PY", "PYG"),)
    assert STORE_CONFIGS["shoppingchina"].market_pairs == (
        ("PY", "PYG"),
        ("PY", "BRL"),
    )
