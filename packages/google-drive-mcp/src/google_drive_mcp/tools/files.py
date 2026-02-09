"""MCP tool functions for Google Drive file operations."""

from __future__ import annotations

import logging
from typing import Any

from google_drive_mcp.client import get_client

logger = logging.getLogger(__name__)


async def list_files(
    folder_id: str | None = None,
    page_size: int = 25,
) -> list[dict[str, Any]]:
    """List files in Google Drive.

    Args:
        folder_id: Optional folder ID to list contents of.
        page_size: Maximum number of files to return.

    Returns:
        List of file metadata dicts.
    """
    client = get_client()
    files = client.list_files(folder_id=folder_id, page_size=page_size)
    logger.info("Listed %d files", len(files))
    return files


async def search_files(
    query: str,
    page_size: int = 25,
) -> list[dict[str, Any]]:
    """Search for files by name in Google Drive.

    Args:
        query: Search query string (matches against file names).
        page_size: Maximum number of files to return.

    Returns:
        List of matching file metadata dicts.
    """
    client = get_client()
    files = client.search_files(query, page_size=page_size)
    logger.info("Search '%s' returned %d files", query, len(files))
    return files


async def read_file(file_id: str) -> str:
    """Read the text content of a file.

    For Google Docs/Sheets/Slides, exports as plain text.
    For other file types, returns raw content as text.

    Args:
        file_id: The ID of the file to read.

    Returns:
        File content as a string.
    """
    client = get_client()
    content = client.read_file(file_id)
    logger.info("Read file %s (%d chars)", file_id, len(content))
    return content


async def create_file(
    name: str,
    mime_type: str = "application/vnd.google-apps.document",
    content: str | None = None,
    parent_folder_id: str | None = None,
) -> dict[str, Any]:
    """Create a new file in Google Drive.

    Args:
        name: File name.
        mime_type: MIME type (e.g. "application/vnd.google-apps.document" for Google Doc,
            "application/vnd.google-apps.spreadsheet" for Google Sheet).
        content: Optional initial text content.
        parent_folder_id: Optional parent folder ID.

    Returns:
        Created file metadata dict.
    """
    client = get_client()
    file = client.create_file(
        name=name, mime_type=mime_type,
        content=content, parent_folder_id=parent_folder_id,
    )
    logger.info("Created file '%s' (id=%s)", name, file.get("id"))
    return file


async def update_file(
    file_id: str,
    name: str | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    """Update a file's metadata or content.

    Args:
        file_id: The ID of the file to update.
        name: New file name.
        content: New text content.

    Returns:
        Updated file metadata dict.
    """
    client = get_client()
    file = client.update_file(file_id, name=name, content=content)
    logger.info("Updated file %s", file_id)
    return file


async def delete_file(file_id: str) -> dict[str, str]:
    """Delete a file from Google Drive.

    Args:
        file_id: The ID of the file to delete.

    Returns:
        Confirmation dict.
    """
    client = get_client()
    client.delete_file(file_id)
    logger.info("Deleted file %s", file_id)
    return {"status": "deleted", "file_id": file_id}
