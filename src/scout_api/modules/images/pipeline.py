"""Image persistence pipeline: download → original Drive → AVIF async."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from scout_api.core.config import Settings, get_settings
from scout_api.core.database import get_session_factory
from scout_api.core.performance import OperationCategory, timed
from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.images.downloader import ImageDownloader
from scout_api.modules.images.drive_client import (
    DriveClientError,
    DriveNotConfiguredError,
    DriveStorage,
    GoogleDriveClient,
)
from scout_api.modules.images.models import ProductImage
from scout_api.modules.images.optimizer import AvifOptimizer
from scout_api.modules.images.repository import ProductImageRepository
from scout_api.modules.images.schemas import ApprovedImageInput

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_avif_executor: ThreadPoolExecutor | None = None
_avif_lock = threading.Lock()


def _get_avif_executor(max_workers: int) -> ThreadPoolExecutor:
    global _avif_executor
    with _avif_lock:
        if _avif_executor is None:
            _avif_executor = ThreadPoolExecutor(
                max_workers=max(1, max_workers),
                thread_name_prefix="avif",
            )
        return _avif_executor


class ImagePipeline:
    """Orchestrates original persistence and AVIF derivation."""

    def __init__(
        self,
        session: Session,
        *,
        drive: DriveStorage | None = None,
        downloader: ImageDownloader | None = None,
        optimizer: AvifOptimizer | None = None,
        settings: Settings | None = None,
        schedule_avif: bool = True,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._drive: DriveStorage = drive or GoogleDriveClient(self._settings)
        self._downloader = downloader or ImageDownloader(self._settings)
        self._optimizer = optimizer or AvifOptimizer(self._settings)
        self._repo = ProductImageRepository(session)
        self._schedule_avif = schedule_avif

    def persist_approved(
        self,
        product_id: UUID,
        images: list[ApprovedImageInput],
    ) -> list[ProductImage]:
        if not images:
            return []
        max_n = self._settings.image_max_per_product
        if len(images) > max_n:
            raise RequestError(
                f"Máximo de {max_n} imagens por produto",
                code="INVALID_REQUEST",
            )
        main_flags = [img.is_main for img in images]
        if sum(1 for flag in main_flags if flag) > 1:
            raise RequestError(
                "No máximo uma imagem pode ser is_main=true",
                code="INVALID_REQUEST",
            )
        # Default first as main when none flagged.
        if images and not any(img.is_main for img in images):
            first = images[0]
            images = [
                ApprovedImageInput(
                    source_url=first.source_url,
                    position=first.position,
                    is_main=True,
                ),
                *images[1:],
            ]

        results: list[ProductImage] = []
        with timed(
            "image_pipeline_batch",
            category=OperationCategory.EXTERNAL_TOOL,
            context={"count": len(images)},
        ):
            for approved in sorted(images, key=lambda i: i.position):
                row = self._persist_one(product_id, approved)
                results.append(row)
        return results

    def _persist_one(
        self, product_id: UUID, approved: ApprovedImageInput
    ) -> ProductImage:
        source_url = str(approved.source_url)
        existing_count = self._repo.count_for_product(product_id)
        if existing_count >= self._settings.image_max_per_product:
            raise RequestError(
                f"Máximo de {self._settings.image_max_per_product} imagens por produto",
                code="INVALID_REQUEST",
            )

        row = self._repo.create(
            product_id=product_id,
            source_url=source_url,
            position=approved.position,
            is_main=approved.is_main,
            original_status="downloading",
            optimized_status="pending",
        )
        try:
            downloaded = self._downloader.download(source_url)
            dup = self._repo.find_by_sha256(product_id, downloaded.sha256)
            if dup is not None and dup.id != row.id:
                # Drop the placeholder and reuse existing.
                self._repo.delete(row)
                return dup

            products_folder = self._drive.ensure_folder(
                "products", parent_id=self._root_folder_id()
            )
            product_folder = self._drive.ensure_folder(
                str(product_id), parent_id=products_folder
            )
            original_folder = self._drive.ensure_folder(
                "original", parent_id=product_folder
            )
            filename = f"{row.id}.{downloaded.extension}"
            with timed(
                "image_original_upload",
                category=OperationCategory.EXTERNAL_TOOL,
            ):
                file_id = self._drive.upload_bytes(
                    name=filename,
                    parent_id=original_folder,
                    data=downloaded.data,
                    mime_type=downloaded.content_type,
                )
            row.original_drive_file_id = file_id
            row.original_filename = filename
            row.original_mime_type = downloaded.content_type
            row.original_size_bytes = len(downloaded.data)
            row.original_width = downloaded.width
            row.original_height = downloaded.height
            row.original_sha256 = downloaded.sha256
            row.original_status = "ready"
            row.optimized_status = "pending"
            self._session.flush()

            if self._schedule_avif:
                self.enqueue_optimization(row.id)
            return row
        except (RequestError, DriveNotConfiguredError, DriveClientError) as exc:
            row.original_status = "failed"
            row.optimized_status = "failed"
            row.optimized_error = str(exc)[:500]
            self._session.flush()
            if isinstance(exc, RequestError):
                raise
            raise RequestError(str(exc), code="STORAGE_ERROR") from exc

    def _root_folder_id(self) -> str:
        if isinstance(self._drive, GoogleDriveClient):
            return self._drive.root_folder_id
        # In-memory / injected storage: use synthetic root.
        root = getattr(self._drive, "root_folder_id", None)
        if callable(root):
            return str(root())
        if isinstance(root, str) and root:
            return root
        # Ensure a root folder entry for InMemoryDriveStorage
        ensure = getattr(self._drive, "ensure_folder", None)
        if ensure is not None and hasattr(self._drive, "folders"):
            # Use a fixed synthetic parent for tests.
            return "root"
        raise DriveNotConfiguredError("Drive root folder ausente")

    def enqueue_optimization(self, image_id: UUID) -> None:
        settings = self._settings
        executor = _get_avif_executor(settings.image_avif_max_concurrency)
        executor.submit(_run_avif_job, str(image_id), settings)

    def optimize_now(self, image: ProductImage) -> ProductImage:
        """Synchronous AVIF (tests / retry path)."""
        if image.original_status != "ready" or not image.original_drive_file_id:
            raise RequestError(
                "Original não está ready para otimização",
                code="INVALID_REQUEST",
            )
        image.optimized_status = "processing"
        image.optimized_error = None
        self._session.flush()
        try:
            original_bytes = self._drive.download_bytes(image.original_drive_file_id)
            optimized = self._optimizer.convert(original_bytes)
            products_folder = self._drive.ensure_folder(
                "products", parent_id=self._root_folder_id()
            )
            product_folder = self._drive.ensure_folder(
                str(image.canonical_product_id), parent_id=products_folder
            )
            opt_folder = self._drive.ensure_folder(
                "optimized", parent_id=product_folder
            )
            filename = f"{image.id}.avif"
            with timed(
                "image_optimized_upload",
                category=OperationCategory.EXTERNAL_TOOL,
            ):
                file_id = self._drive.upload_bytes(
                    name=filename,
                    parent_id=opt_folder,
                    data=optimized.data,
                    mime_type=optimized.mime_type,
                )
            image.optimized_drive_file_id = file_id
            image.optimized_mime_type = optimized.mime_type
            image.optimized_size_bytes = optimized.size_bytes
            image.optimized_width = optimized.width
            image.optimized_height = optimized.height
            image.optimized_status = "ready"
            image.optimized_error = None
            self._session.flush()
            return image
        except Exception as exc:
            logger.exception("AVIF failed for image %s", image.id)
            image.optimized_status = "failed"
            image.optimized_error = str(exc)[:500]
            self._session.flush()
            return image

    def delete_image_files(self, image: ProductImage) -> None:
        for file_id in (
            image.optimized_drive_file_id,
            image.original_drive_file_id,
        ):
            if not file_id:
                continue
            try:
                self._drive.delete_file(file_id)
            except DriveClientError as exc:
                if "DRIVE_FILE_NOT_FOUND" in str(exc):
                    continue
                raise


def _run_avif_job(image_id: str, settings: Settings) -> None:
    """Background worker: open a fresh DB session and optimize."""
    try:
        SessionLocal = get_session_factory()
        with SessionLocal() as session:
            repo = ProductImageRepository(session)
            row = repo.get(UUID(image_id))
            if row is None or row.original_status != "ready":
                return
            if row.optimized_status == "ready":
                return
            drive = GoogleDriveClient(settings)
            pipeline = ImagePipeline(
                session,
                drive=drive,
                settings=settings,
                schedule_avif=False,
            )
            pipeline.optimize_now(row)
            session.commit()
    except Exception:
        logger.exception("Background AVIF job failed for %s", image_id)
