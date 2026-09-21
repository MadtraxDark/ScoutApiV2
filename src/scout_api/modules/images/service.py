"""Product image gallery service (CRUD, delivery, cleanup)."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from scout_api.core.config import Settings, get_settings
from scout_api.modules.auth.schemas import AuthenticatedPrincipal
from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.images.drive_client import (
    DriveClientError,
    DriveStorage,
    GoogleDriveClient,
    InMemoryDriveStorage,
)
from scout_api.modules.images.models import ProductImage
from scout_api.modules.images.pipeline import ImagePipeline
from scout_api.modules.images.repository import ProductImageRepository
from scout_api.modules.images.schemas import (
    AddProductImageRequest,
    ApprovedImageInput,
    GalleryPatchRequest,
    ProductImageListResponse,
    ProductImageView,
)
from scout_api.modules.matching.repository import MatchingRepository

logger = logging.getLogger(__name__)


def content_path(product_id: UUID, image_id: UUID) -> str:
    return f"/products/{product_id}/images/{image_id}/content"


def to_image_view(row: ProductImage) -> ProductImageView:
    product_id = row.canonical_product_id
    original_url = (
        content_path(product_id, row.id) if row.original_status == "ready" else None
    )
    optimized_url = (
        content_path(product_id, row.id)
        if row.optimized_status == "ready"
        else None
    )
    if row.optimized_status == "ready":
        display_url = optimized_url
    elif row.original_status == "ready":
        display_url = original_url
    else:
        display_url = None
    return ProductImageView(
        image_id=row.id,
        product_id=product_id,
        position=row.position,
        is_main=row.is_main,
        source_url=row.source_url,
        original_url=original_url,
        optimized_url=optimized_url,
        display_url=display_url,
        original_status=row.original_status,  # type: ignore[arg-type]
        optimized_status=row.optimized_status,  # type: ignore[arg-type]
        original_width=row.original_width,
        original_height=row.original_height,
        optimized_error=row.optimized_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ProductImageService:
    def __init__(
        self,
        session: Session,
        *,
        drive: DriveStorage | None = None,
        settings: Settings | None = None,
        schedule_avif: bool = True,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        if drive is not None:
            self._drive = drive
        elif self._settings.google_drive_refresh_token:
            self._drive = GoogleDriveClient(self._settings)
        else:
            # Dev/test without Drive credentials: in-memory (non-persistent).
            self._drive = InMemoryDriveStorage()
        self._repo = ProductImageRepository(session)
        self._pipeline = ImagePipeline(
            session,
            drive=self._drive,
            settings=self._settings,
            schedule_avif=schedule_avif,
        )

    def _require_product(
        self, product_id: UUID, principal: AuthenticatedPrincipal
    ) -> None:
        from scout_api.modules.matching.product_registration_service import (
            can_access_product,
        )

        matching = MatchingRepository(self._session)
        product = matching.get_canonical(product_id)
        if product is None or not can_access_product(product, principal):
            raise RequestError(
                "Produto canônico não encontrado",
                code="PRODUCT_NOT_FOUND",
            )

    def list_images(
        self, product_id: UUID, *, viewer: AuthenticatedPrincipal
    ) -> ProductImageListResponse:
        self._require_product(product_id, viewer)
        rows = self._repo.list_for_product(product_id)
        items = [to_image_view(row) for row in rows]
        return ProductImageListResponse(items=items, count=len(items))

    def persist_approved(
        self,
        product_id: UUID,
        images: list[ApprovedImageInput],
        *,
        owner: AuthenticatedPrincipal,
    ) -> list[ProductImageView]:
        self._require_product(product_id, owner)
        rows = self._pipeline.persist_approved(product_id, images)
        return [to_image_view(row) for row in rows]

    def add_image(
        self,
        product_id: UUID,
        request: AddProductImageRequest,
        *,
        owner: AuthenticatedPrincipal,
    ) -> ProductImageView:
        self._require_product(product_id, owner)
        position = (
            request.position
            if request.position is not None
            else self._repo.next_position(product_id)
        )
        approved = ApprovedImageInput(
            source_url=request.source_url,
            position=position,
            is_main=request.is_main,
        )
        rows = self._pipeline.persist_approved(product_id, [approved])
        return to_image_view(rows[0])

    def patch_gallery(
        self,
        product_id: UUID,
        request: GalleryPatchRequest,
        *,
        owner: AuthenticatedPrincipal,
    ) -> ProductImageListResponse:
        self._require_product(product_id, owner)
        try:
            rows = self._repo.apply_positions(
                product_id,
                [
                    (item.image_id, item.position, item.is_main)
                    for item in request.images
                ],
            )
        except ValueError as exc:
            raise RequestError(str(exc), code="INVALID_REQUEST") from exc
        items = [to_image_view(row) for row in rows]
        return ProductImageListResponse(items=items, count=len(items))

    def delete_image(
        self,
        product_id: UUID,
        image_id: UUID,
        *,
        owner: AuthenticatedPrincipal,
    ) -> None:
        self._require_product(product_id, owner)
        row = self._repo.get(image_id, product_id=product_id)
        if row is None:
            return
        row.original_status = "deleting"
        self._session.flush()
        try:
            self._pipeline.delete_image_files(row)
        except DriveClientError as exc:
            logger.error(
                "Drive cleanup failed for image %s: %s", image_id, exc
            )
            # Keep deleting marker for retry; still remove DB row only if files gone
            # Prefer leaving row so operator can retry — but plan says allow retry.
            raise RequestError(
                "Falha parcial ao excluir arquivos no Drive; tente novamente",
                code="STORAGE_ERROR",
                retryable=True,
            ) from exc
        was_main = row.is_main
        self._repo.delete(row)
        self._repo.resequence(product_id)
        if was_main:
            remaining = self._repo.list_for_product(product_id)
            if remaining and not any(r.is_main for r in remaining):
                self._repo.set_main(remaining[0])

    def retry_optimization(
        self,
        product_id: UUID,
        image_id: UUID,
        *,
        owner: AuthenticatedPrincipal,
        sync: bool = False,
    ) -> ProductImageView:
        self._require_product(product_id, owner)
        row = self._repo.get(image_id, product_id=product_id)
        if row is None:
            raise RequestError(
                "Imagem não encontrada",
                code="PRODUCT_NOT_FOUND",
            )
        if row.original_status != "ready":
            raise RequestError(
                "Original não está ready",
                code="INVALID_REQUEST",
            )
        row.optimized_status = "pending"
        row.optimized_error = None
        self._session.flush()
        if sync:
            self._pipeline.optimize_now(row)
        else:
            self._pipeline.enqueue_optimization(row.id)
        refreshed = self._repo.get(image_id, product_id=product_id)
        assert refreshed is not None
        return to_image_view(refreshed)

    def get_content(
        self,
        product_id: UUID,
        image_id: UUID,
        *,
        viewer: AuthenticatedPrincipal,
    ) -> tuple[bytes, str, str]:
        """Return (bytes, content_type, etag)."""
        self._require_product(product_id, viewer)
        row = self._repo.get(image_id, product_id=product_id)
        if row is None:
            raise RequestError("Imagem não encontrada", code="PRODUCT_NOT_FOUND")
        if row.optimized_status == "ready" and row.optimized_drive_file_id:
            data = self._drive.download_bytes(row.optimized_drive_file_id)
            ctype = row.optimized_mime_type or "image/avif"
            etag = row.original_sha256 or str(row.id)
            return data, ctype, f'"{etag}-avif"'
        if row.original_status == "ready" and row.original_drive_file_id:
            data = self._drive.download_bytes(row.original_drive_file_id)
            ctype = row.original_mime_type or "application/octet-stream"
            etag = row.original_sha256 or str(row.id)
            return data, ctype, f'"{etag}-original"'
        raise RequestError(
            "Imagem ainda não disponível",
            code="INVALID_REQUEST",
        )

    def cleanup_product_images(self, product_id: UUID) -> None:
        """Best-effort Drive cleanup before product cascade delete."""
        rows = self._repo.list_for_product(product_id)
        for row in rows:
            try:
                self._pipeline.delete_image_files(row)
            except DriveClientError:
                logger.exception(
                    "Failed Drive cleanup for image %s on product delete",
                    row.id,
                )
