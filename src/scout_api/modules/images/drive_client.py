"""Google Drive API client for the dedicated PriceScout storage account."""

from __future__ import annotations

import io
import logging
from typing import Any, Protocol

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from scout_api.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveStorage(Protocol):
    def ensure_folder(self, name: str, *, parent_id: str) -> str: ...

    def upload_bytes(
        self,
        *,
        name: str,
        parent_id: str,
        data: bytes,
        mime_type: str,
    ) -> str: ...

    def download_bytes(self, file_id: str) -> bytes: ...

    def delete_file(self, file_id: str) -> None: ...


class DriveNotConfiguredError(RuntimeError):
    """Raised when Google Drive OAuth settings are incomplete."""


class DriveClientError(RuntimeError):
    """Wrapped Drive API failure."""


class GoogleDriveClient:
    """Drive v3 client using offline OAuth refresh token (backend-only)."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        service: Any | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._service = service

    @property
    def root_folder_id(self) -> str:
        folder_id = (self._settings.google_drive_root_folder_id or "").strip()
        if not folder_id:
            raise DriveNotConfiguredError(
                "GOOGLE_DRIVE_ROOT_FOLDER_ID não configurado"
            )
        return folder_id

    def is_configured(self) -> bool:
        s = self._settings
        return bool(
            (s.google_drive_client_id or "").strip()
            and (s.google_drive_client_secret or "").strip()
            and (s.google_drive_refresh_token or "").strip()
            and (s.google_drive_root_folder_id or "").strip()
        )

    def _credentials(self) -> Credentials:
        s = self._settings
        client_id = (s.google_drive_client_id or "").strip()
        client_secret = (s.google_drive_client_secret or "").strip()
        refresh_token = (s.google_drive_refresh_token or "").strip()
        if not (client_id and client_secret and refresh_token):
            raise DriveNotConfiguredError(
                "Credenciais Google Drive incompletas "
                "(CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN)"
            )
        creds = Credentials(  # type: ignore[no-untyped-call]
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=[DRIVE_SCOPE],
        )
        if not creds.valid:
            creds.refresh(Request())  # type: ignore[no-untyped-call]
        return creds

    def _drive(self) -> Any:
        if self._service is not None:
            return self._service
        creds = self._credentials()
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def ensure_folder(self, name: str, *, parent_id: str) -> str:
        """Find or create a folder under parent (drive.file scoped)."""
        safe_name = name.replace("'", "\\'")
        query = (
            f"name = '{safe_name}' and '{parent_id}' in parents "
            f"and mimeType = '{FOLDER_MIME}' and trashed = false"
        )
        try:
            existing = (
                self._drive()
                .files()
                .list(q=query, spaces="drive", fields="files(id,name)", pageSize=1)
                .execute()
            )
            files = existing.get("files") or []
            if files:
                return str(files[0]["id"])
            meta = {
                "name": name,
                "mimeType": FOLDER_MIME,
                "parents": [parent_id],
            }
            created = (
                self._drive()
                .files()
                .create(body=meta, fields="id")
                .execute()
            )
            return str(created["id"])
        except HttpError as exc:
            raise DriveClientError(f"Falha ao garantir pasta Drive: {exc}") from exc

    def upload_bytes(
        self,
        *,
        name: str,
        parent_id: str,
        data: bytes,
        mime_type: str,
    ) -> str:
        media = MediaIoBaseUpload(
            io.BytesIO(data), mimetype=mime_type, resumable=False
        )
        body = {"name": name, "parents": [parent_id]}
        try:
            created = (
                self._drive()
                .files()
                .create(body=body, media_body=media, fields="id")
                .execute()
            )
            return str(created["id"])
        except HttpError as exc:
            raise DriveClientError(f"Falha no upload Drive: {exc}") from exc

    def download_bytes(self, file_id: str) -> bytes:
        try:
            request = self._drive().files().get_media(fileId=file_id)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buffer.getvalue()
        except HttpError as exc:
            if getattr(exc, "resp", None) is not None and exc.resp.status == 404:
                raise DriveClientError("DRIVE_FILE_NOT_FOUND") from exc
            raise DriveClientError(f"Falha no download Drive: {exc}") from exc

    def delete_file(self, file_id: str) -> None:
        """Idempotent delete: missing file is success."""
        try:
            self._drive().files().delete(fileId=file_id).execute()
        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status == 404:
                logger.info("Drive file already absent: %s", file_id[:8])
                return
            raise DriveClientError(f"Falha ao excluir arquivo Drive: {exc}") from exc


class InMemoryDriveStorage:
    """Test double that stores bytes in process memory."""

    root_folder_id: str = "root"

    def __init__(self) -> None:
        self.files: dict[str, tuple[str, bytes, str]] = {}
        self.folders: dict[tuple[str, str], str] = {}
        self._seq = 0

    def _next_id(self) -> str:
        self._seq += 1
        return f"mem-{self._seq}"

    def ensure_folder(self, name: str, *, parent_id: str) -> str:
        key = (parent_id, name)
        if key not in self.folders:
            self.folders[key] = self._next_id()
        return self.folders[key]

    def upload_bytes(
        self,
        *,
        name: str,
        parent_id: str,
        data: bytes,
        mime_type: str,
    ) -> str:
        file_id = self._next_id()
        self.files[file_id] = (name, data, mime_type)
        return file_id

    def download_bytes(self, file_id: str) -> bytes:
        if file_id not in self.files:
            raise DriveClientError("DRIVE_FILE_NOT_FOUND")
        return self.files[file_id][1]

    def delete_file(self, file_id: str) -> None:
        self.files.pop(file_id, None)
