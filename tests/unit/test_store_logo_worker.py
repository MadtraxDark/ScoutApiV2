from __future__ import annotations

import io
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from scout_api.core.config import Settings
from scout_api.modules.images.drive_client import InMemoryDriveStorage
from scout_api.modules.matching.db import create_all
from scout_api.modules.matching.models import StoreMetadata
from scout_api.modules.matching.store_logo_worker import process_store_logo_jobs


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (20, 12), (20, 40, 60, 100)).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def logo_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _queued_logo(session: Session, drive: InMemoryDriveStorage) -> StoreMetadata:
    folder = drive.ensure_folder("store-logos", parent_id=drive.root_folder_id)
    original_id = drive.upload_bytes(
        name="logo.png", parent_id=folder, data=_png(), mime_type="image/png"
    )
    row = StoreMetadata(
        store_key="kabum",
        logo_mime_type="image/png",
        logo_original_file_id=original_id,
        logo_processing_status="pending",
        logo_version=str(uuid4()),
    )
    session.add(row)
    session.commit()
    return row


def test_store_logo_worker_optimizes_idempotently_and_keeps_original(
    logo_session: Session,
) -> None:
    drive = InMemoryDriveStorage()
    row = _queued_logo(logo_session, drive)
    original_id = row.logo_original_file_id
    settings = Settings(image_optimization_batch_size=5)

    assert process_store_logo_jobs(logo_session, drive=drive, settings=settings) == 1
    logo_session.refresh(row)
    assert row.logo_processing_status == "ready"
    assert row.logo_original_file_id == original_id
    assert row.logo_optimized_file_id is not None
    assert row.logo_optimized_file_id != original_id
    assert process_store_logo_jobs(logo_session, drive=drive, settings=settings) == 0

    optimized = drive.download_bytes(row.logo_optimized_file_id)
    with Image.open(io.BytesIO(optimized)) as image:
        assert "A" in image.getbands()
        assert image.size == (20, 12)


def test_store_logo_worker_failure_keeps_original_and_marks_failed(
    logo_session: Session,
) -> None:
    class FailingDrive(InMemoryDriveStorage):
        def upload_bytes(self, **kwargs: object) -> str:
            if kwargs.get("name") == "logo.png":
                return super().upload_bytes(**kwargs)  # type: ignore[arg-type]
            raise RuntimeError("storage unavailable")

    drive = FailingDrive()
    row = _queued_logo(logo_session, drive)
    original_id = row.logo_original_file_id

    assert process_store_logo_jobs(logo_session, drive=drive) == 0
    logo_session.refresh(row)
    assert row.logo_processing_status == "failed"
    assert row.logo_original_file_id == original_id
    assert drive.download_bytes(original_id) == _png()


def test_old_logo_job_cannot_replace_a_newer_upload(logo_session: Session) -> None:
    class UploadChangesVersion(InMemoryDriveStorage):
        session: Session

        def upload_bytes(self, **kwargs: object) -> str:
            file_id = super().upload_bytes(**kwargs)  # type: ignore[arg-type]
            if kwargs.get("name") == "logo.png":
                return file_id
            row = self.session.get(StoreMetadata, "kabum")
            assert row is not None
            row.logo_version = "new-version"
            row.logo_processing_status = "pending"
            self.session.commit()
            return file_id

    drive = UploadChangesVersion()
    drive.session = logo_session
    row = _queued_logo(logo_session, drive)
    old_version = row.logo_version

    assert process_store_logo_jobs(logo_session, drive=drive) == 0
    logo_session.refresh(row)
    assert row.logo_version == "new-version"
    assert row.logo_version != old_version
    assert row.logo_processing_status == "pending"
    assert row.logo_optimized_file_id is None
    assert len(drive.files) == 1
