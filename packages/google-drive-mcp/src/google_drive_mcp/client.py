"""Google Drive API client using service account authentication."""

from __future__ import annotations

import io
import logging
import os
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


class GoogleDriveClient:
    """Wrapper around the Google Drive v3 API using a service account."""

    def __init__(self, key_file: str | None = None) -> None:
        key_path = key_file or os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE", "")
        if not key_path:
            raise ValueError(
                "Google service account key file is required. "
                "Set the GOOGLE_SERVICE_ACCOUNT_KEY_FILE environment variable."
            )
        credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=SCOPES,
        )
        self._service = build("drive", "v3", credentials=credentials)
        logger.info("GoogleDriveClient initialised with key file: %s", key_path)

    def list_files(
        self,
        query: str | None = None,
        folder_id: str | None = None,
        page_size: int = 25,
    ) -> list[dict[str, Any]]:
        """List files, optionally filtered by query or folder."""
        q_parts: list[str] = ["trashed = false"]
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        if query:
            q_parts.append(query)

        result = self._service.files().list(
            q=" and ".join(q_parts),
            pageSize=page_size,
            fields="files(id, name, mimeType, webViewLink, modifiedTime, size)",
            orderBy="modifiedTime desc",
        ).execute()
        return result.get("files", [])

    def search_files(self, name_query: str, page_size: int = 25) -> list[dict[str, Any]]:
        """Search for files by name."""
        safe_query = name_query.replace("'", "\\'")
        return self.list_files(
            query=f"name contains '{safe_query}'",
            page_size=page_size,
        )

    def read_file(self, file_id: str) -> str:
        """Read file content. Exports Google Docs formats as plain text."""
        meta = self._service.files().get(fileId=file_id, fields="mimeType").execute()
        mime_type = meta.get("mimeType", "")

        if mime_type.startswith("application/vnd.google-apps."):
            response = self._service.files().export(
                fileId=file_id, mimeType="text/plain",
            ).execute()
            return response.decode("utf-8") if isinstance(response, bytes) else str(response)

        response = self._service.files().get_media(fileId=file_id).execute()
        return response.decode("utf-8") if isinstance(response, bytes) else str(response)

    def create_file(
        self,
        name: str,
        mime_type: str = "application/vnd.google-apps.document",
        content: str | None = None,
        parent_folder_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new file."""
        body: dict[str, Any] = {"name": name, "mimeType": mime_type}
        if parent_folder_id:
            body["parents"] = [parent_folder_id]

        if content:
            media = MediaIoBaseUpload(
                io.BytesIO(content.encode("utf-8")),
                mimetype="text/plain",
            )
            return self._service.files().create(
                body=body, media_body=media,
                fields="id, name, mimeType, webViewLink, modifiedTime",
            ).execute()

        return self._service.files().create(
            body=body,
            fields="id, name, mimeType, webViewLink, modifiedTime",
        ).execute()

    def update_file(
        self,
        file_id: str,
        name: str | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        """Update a file's metadata or content."""
        body: dict[str, Any] = {}
        if name:
            body["name"] = name

        kwargs: dict[str, Any] = {
            "fileId": file_id,
            "fields": "id, name, mimeType, webViewLink, modifiedTime",
        }
        if body:
            kwargs["body"] = body
        if content:
            kwargs["media_body"] = MediaIoBaseUpload(
                io.BytesIO(content.encode("utf-8")),
                mimetype="text/plain",
            )

        return self._service.files().update(**kwargs).execute()

    def delete_file(self, file_id: str) -> None:
        """Delete a file (move to trash)."""
        self._service.files().delete(fileId=file_id).execute()


# Module-level singleton
_client: GoogleDriveClient | None = None


def get_client() -> GoogleDriveClient:
    """Return the module-level GoogleDriveClient singleton."""
    global _client
    if _client is None:
        _client = GoogleDriveClient()
    return _client
