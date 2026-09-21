"""Unit tests for product images (Drive mock, SSRF, AVIF fallback, gallery)."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scout_api.modules.auth.schemas import AuthenticatedPrincipal, UserRole
from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.images.downloader import (
    ImageDownloader,
    assert_url_safe_for_download,
    validate_image_bytes,
)
from scout_api.modules.images.drive_client import (
    DriveClientError,
    GoogleDriveClient,
    InMemoryDriveStorage,
)
from scout_api.modules.images.optimizer import AvifOptimizer
from scout_api.modules.images.pipeline import ImagePipeline
from scout_api.modules.images.schemas import (
    AddProductImageRequest,
    ApprovedImageInput,
    GalleryPatchRequest,
    GalleryReorderItem,
)
from scout_api.modules.images.service import ProductImageService, to_image_view
from scout_api.modules.matching.db import create_all
from scout_api.modules.matching.product_registration_service import (
    ProductRegistrationService,
)
from scout_api.modules.matching.schemas import ProductRegisterRequest

_OWNER = AuthenticatedPrincipal(
    id=UUID("11111111-1111-4111-8111-111111111111"),
    role=UserRole.USER,
    display_name="tester",
)


def _png_bytes(color: tuple[int, int, int] = (255, 0, 0), size: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buf, format="PNG")
    return buf.getvalue()


def _rgba_png_bytes(size: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (size, size), (0, 128, 255, 128)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def drive() -> InMemoryDriveStorage:
    return InMemoryDriveStorage()


def test_drive_inmemory_upload_download_delete(drive: InMemoryDriveStorage) -> None:
    folder = drive.ensure_folder("original", parent_id=drive.root_folder_id)
    file_id = drive.upload_bytes(
        name="a.png", parent_id=folder, data=b"abc", mime_type="image/png"
    )
    assert drive.download_bytes(file_id) == b"abc"
    drive.delete_file(file_id)
    with pytest.raises(DriveClientError, match="DRIVE_FILE_NOT_FOUND"):
        drive.download_bytes(file_id)
    drive.delete_file("missing")  # idempotent


def test_google_drive_client_refresh_and_upload() -> None:
    service = MagicMock()
    files = service.files.return_value
    files.list.return_value.execute.return_value = {"files": []}
    files.create.return_value.execute.return_value = {"id": "folder-1"}
    # Second create = upload
    files.create.return_value.execute.side_effect = [
        {"id": "folder-1"},
        {"id": "file-9"},
    ]
    client = GoogleDriveClient(service=service)
    with patch.object(client, "_credentials", return_value=MagicMock()):
        folder = client.ensure_folder("x", parent_id="root")
        assert folder == "folder-1"
        file_id = client.upload_bytes(
            name="a.png", parent_id=folder, data=b"hi", mime_type="image/png"
        )
        assert file_id == "file-9"


def test_google_drive_delete_404_is_ok() -> None:
    service = MagicMock()
    from googleapiclient.errors import HttpError

    resp = MagicMock()
    resp.status = 404
    http_err = HttpError(resp, b"not found")
    service.files.return_value.delete.return_value.execute.side_effect = http_err
    client = GoogleDriveClient(service=service)
    client.delete_file("gone")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x.png",
        "http://localhost/x.png",
        "http://[::1]/x.png",
        "http://169.254.169.254/latest/meta-data",
        "ftp://example.com/x.png",
    ],
)
def test_ssrf_blocked_literal(url: str) -> None:
    with pytest.raises(RequestError):
        assert_url_safe_for_download(url)


def test_ssrf_blocked_private_dns() -> None:
    with patch(
        "scout_api.modules.images.downloader.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("10.0.0.5", 0))],
    ):
        with pytest.raises(RequestError, match="privada"):
            assert_url_safe_for_download("https://evil.example/x.png")


def test_validate_rejects_non_image() -> None:
    with pytest.raises(RequestError, match="não é uma imagem"):
        validate_image_bytes(
            b"not-an-image",
            claimed_content_type="image/png",
            max_dimension=4096,
        )


def test_validate_accepts_png_and_rgba() -> None:
    mime, w, h, ext = validate_image_bytes(
        _png_bytes(), claimed_content_type="text/html", max_dimension=4096
    )
    assert mime.startswith("image/")
    assert w == 32 and h == 32 and ext == "png"
    mime2, _, _, _ = validate_image_bytes(
        _rgba_png_bytes(), claimed_content_type="image/png", max_dimension=4096
    )
    assert mime2.startswith("image/")


def test_downloader_redirect_to_private_blocked() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.url.host == "cdn.example":
            return httpx.Response(
                302, headers={"Location": "http://127.0.0.1/secret.png"}
            )
        return httpx.Response(200, content=_png_bytes())

    transport = httpx.MockTransport(handler)
    downloader = ImageDownloader()

    real_client = httpx.Client(transport=transport, follow_redirects=False)

    class _Ctx:
        def __enter__(self) -> httpx.Client:
            return real_client

        def __exit__(self, *args: object) -> None:
            return None

    def fake_getaddrinfo(host: str, *args: object, **kwargs: object):
        if host in {"127.0.0.1", "localhost"}:
            return [(2, 1, 6, "", ("127.0.0.1", 0))]
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    with (
        patch(
            "scout_api.modules.images.downloader.socket.getaddrinfo",
            side_effect=fake_getaddrinfo,
        ),
        patch("httpx.Client", return_value=_Ctx()),
    ):
        with pytest.raises(RequestError):
            downloader.download("https://cdn.example/photo.png")
    assert calls["n"] >= 1


def test_display_url_fallback_rules(
    session: Session, drive: InMemoryDriveStorage
) -> None:
    reg = ProductRegistrationService(session)
    created = reg.register(
        ProductRegisterRequest(title="Cam", brand="Acme", gtin="7891991010863"),
        owner=_OWNER,
    )
    product_id = created.product.id
    svc = ProductImageService(
        session, drive=drive, schedule_avif=False
    )
    png = _png_bytes()

    def fake_download(url: str):
        import hashlib

        from scout_api.modules.images.downloader import DownloadedImage

        return DownloadedImage(
            data=png,
            content_type="image/png",
            width=32,
            height=32,
            sha256=hashlib.sha256(png).hexdigest(),
            extension="png",
            source_url=url,
        )

    with patch.object(
        svc._pipeline._downloader, "download", side_effect=fake_download
    ):
        view = svc.add_image(
            product_id,
            AddProductImageRequest(
                source_url="https://cdn.example/a.png", is_main=True
            ),
            owner=_OWNER,
        )
    assert view.original_status == "ready"
    assert view.optimized_status == "pending"
    assert view.display_url == view.original_url
    assert view.display_url and view.display_url.endswith("/content")

    # Mark optimized ready → prefer AVIF path (same content URL, different etag)
    from scout_api.modules.images.repository import ProductImageRepository

    row = ProductImageRepository(session).get(view.image_id)
    assert row is not None
    row.optimized_status = "ready"
    row.optimized_drive_file_id = row.original_drive_file_id
    row.optimized_mime_type = "image/avif"
    session.flush()
    ready = to_image_view(row)
    assert ready.display_url == ready.optimized_url

    row.optimized_status = "failed"
    session.flush()
    failed = to_image_view(row)
    assert failed.display_url == failed.original_url


def test_approval_persists_only_selected(
    session: Session, drive: InMemoryDriveStorage
) -> None:
    reg = ProductRegistrationService(session)
    product = reg.register(
        ProductRegisterRequest(title="Phone", gtin="7891991010863"),
        owner=_OWNER,
    ).product
    svc = ProductImageService(session, drive=drive, schedule_avif=False)
    pngs = [_png_bytes(color=(i * 40, 0, 0)) for i in range(5)]

    def fake_download(url: str):
        import hashlib

        from scout_api.modules.images.downloader import DownloadedImage

        idx = int(url.rstrip(".png").split("/")[-1])
        data = pngs[idx]
        return DownloadedImage(
            data=data,
            content_type="image/png",
            width=32,
            height=32,
            sha256=hashlib.sha256(data).hexdigest(),
            extension="png",
            source_url=url,
        )

    approved = [
        ApprovedImageInput(
            source_url=f"https://cdn.example/{i}.png",
            position=i,
            is_main=(i == 0),
        )
        for i in (0, 2, 4)
    ]
    with patch.object(
        svc._pipeline._downloader, "download", side_effect=fake_download
    ):
        views = svc.persist_approved(product.id, approved, owner=_OWNER)
    assert len(views) == 3
    assert len(drive.files) == 3
    listed = svc.list_images(product.id, viewer=_OWNER)
    assert listed.count == 3


def test_reorder_main_delete(session: Session, drive: InMemoryDriveStorage) -> None:
    reg = ProductRegistrationService(session)
    product = reg.register(
        ProductRegisterRequest(title="Phone", gtin="7891991010863"),
        owner=_OWNER,
    ).product
    svc = ProductImageService(session, drive=drive, schedule_avif=False)

    def fake_download(url: str):
        import hashlib

        from scout_api.modules.images.downloader import DownloadedImage

        data = _png_bytes(color=(hash(url) % 200, 10, 10))
        return DownloadedImage(
            data=data,
            content_type="image/png",
            width=32,
            height=32,
            sha256=hashlib.sha256(data).hexdigest(),
            extension="png",
            source_url=url,
        )

    with patch.object(
        svc._pipeline._downloader, "download", side_effect=fake_download
    ):
        a = svc.add_image(
            product.id,
            AddProductImageRequest(
                source_url="https://cdn.example/a.png", is_main=True
            ),
            owner=_OWNER,
        )
        b = svc.add_image(
            product.id,
            AddProductImageRequest(source_url="https://cdn.example/b.png"),
            owner=_OWNER,
        )
    patched = svc.patch_gallery(
        product.id,
        GalleryPatchRequest(
            images=[
                GalleryReorderItem(image_id=b.image_id, position=0, is_main=True),
                GalleryReorderItem(image_id=a.image_id, position=1, is_main=False),
            ]
        ),
        owner=_OWNER,
    )
    assert patched.items[0].image_id == b.image_id
    assert patched.items[0].is_main is True
    svc.delete_image(product.id, b.image_id, owner=_OWNER)
    remaining = svc.list_images(product.id, viewer=_OWNER)
    assert remaining.count == 1
    assert remaining.items[0].image_id == a.image_id
    assert remaining.items[0].is_main is True


def test_avif_failure_keeps_original(
    session: Session, drive: InMemoryDriveStorage
) -> None:
    reg = ProductRegistrationService(session)
    product = reg.register(
        ProductRegisterRequest(title="Phone", gtin="7891991010863"),
        owner=_OWNER,
    ).product
    pipeline = ImagePipeline(
        session, drive=drive, schedule_avif=False
    )

    def fake_download(url: str):
        import hashlib

        from scout_api.modules.images.downloader import DownloadedImage

        data = _png_bytes()
        return DownloadedImage(
            data=data,
            content_type="image/png",
            width=32,
            height=32,
            sha256=hashlib.sha256(data).hexdigest(),
            extension="png",
            source_url=url,
        )

    with patch.object(pipeline._downloader, "download", side_effect=fake_download):
        rows = pipeline.persist_approved(
            product.id,
            [
                ApprovedImageInput(
                    source_url="https://cdn.example/x.png",
                    position=0,
                    is_main=True,
                )
            ],
        )
    row = rows[0]
    assert row.original_status == "ready"
    with patch.object(
        pipeline._optimizer,
        "convert",
        side_effect=RuntimeError("avif boom"),
    ):
        pipeline.optimize_now(row)
    assert row.original_status == "ready"
    assert row.optimized_status == "failed"
    assert row.original_drive_file_id
    assert drive.files[row.original_drive_file_id][1] == _png_bytes()


def test_avif_optimizer_no_upscale() -> None:
    opt = AvifOptimizer()
    small = _png_bytes(size=64)
    try:
        result = opt.convert(small, max_dimension=4096)
    except Exception as exc:
        # Some environments may lack AVIF encoder in Pillow wheel.
        pytest.skip(f"AVIF encoder unavailable: {exc}")
    assert result.width == 64
    assert result.height == 64
    assert result.mime_type == "image/avif"
