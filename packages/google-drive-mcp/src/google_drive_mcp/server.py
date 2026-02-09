"""FastMCP server exposing Google Drive operations as MCP tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from google_drive_mcp.tools.files import (
    list_files as _list_files,
    search_files as _search_files,
    read_file as _read_file,
    create_file as _create_file,
    update_file as _update_file,
    delete_file as _delete_file,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("google-drive")

# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_drive_files(
    folder_id: str | None = None,
    page_size: int = 25,
) -> str:
    """List files in Google Drive.

    Args:
        folder_id: Optional folder ID to list contents of. If not specified, lists root.
        page_size: Maximum number of files to return.
    """
    result = await _list_files(folder_id=folder_id, page_size=page_size)
    return json.dumps(result)


@mcp.tool()
async def search_drive_files(
    query: str,
    page_size: int = 25,
) -> str:
    """Search for files by name in Google Drive.

    Args:
        query: Search query string — matches against file names.
        page_size: Maximum number of results to return.
    """
    result = await _search_files(query=query, page_size=page_size)
    return json.dumps(result)


@mcp.tool()
async def read_drive_file(file_id: str) -> str:
    """Read the text content of a Google Drive file.

    For Google Docs/Sheets/Slides, exports as plain text.
    For other file types, returns raw content as text.

    Args:
        file_id: The ID of the file to read.
    """
    return await _read_file(file_id=file_id)


@mcp.tool()
async def create_drive_file(
    name: str,
    mime_type: str = "application/vnd.google-apps.document",
    content: str | None = None,
    parent_folder_id: str | None = None,
) -> str:
    """Create a new file in Google Drive.

    Args:
        name: File name.
        mime_type: MIME type. Common values:
            - "application/vnd.google-apps.document" (Google Doc)
            - "application/vnd.google-apps.spreadsheet" (Google Sheet)
            - "application/vnd.google-apps.folder" (Folder)
            - "text/plain" (Plain text file)
        content: Optional initial text content for the file.
        parent_folder_id: Optional parent folder ID.
    """
    result = await _create_file(
        name=name, mime_type=mime_type,
        content=content, parent_folder_id=parent_folder_id,
    )
    return json.dumps(result)


@mcp.tool()
async def update_drive_file(
    file_id: str,
    name: str | None = None,
    content: str | None = None,
) -> str:
    """Update a file in Google Drive (rename or change content).

    Args:
        file_id: The ID of the file to update.
        name: New file name.
        content: New text content for the file.
    """
    result = await _update_file(file_id=file_id, name=name, content=content)
    return json.dumps(result)


@mcp.tool()
async def delete_drive_file(file_id: str) -> str:
    """Delete a file from Google Drive.

    Args:
        file_id: The ID of the file to delete.
    """
    result = await _delete_file(file_id=file_id)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Google Drive MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
