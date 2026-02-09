"""Tests for Google Drive MCP file tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from google_drive_mcp.tools.files import (
    list_files,
    search_files,
    read_file,
    create_file,
    update_file,
    delete_file,
)


@pytest.fixture
def mock_client():
    """Fixture providing a mocked GoogleDriveClient."""
    client = MagicMock()
    with patch("google_drive_mcp.tools.files.get_client", return_value=client):
        yield client


@pytest.mark.unit
async def test_list_files(mock_client):
    mock_client.list_files.return_value = [
        {"id": "f1", "name": "doc.txt", "mimeType": "text/plain"},
    ]
    result = await list_files()
    assert len(result) == 1
    assert result[0]["name"] == "doc.txt"
    mock_client.list_files.assert_called_once()


@pytest.mark.unit
async def test_list_files_with_folder(mock_client):
    mock_client.list_files.return_value = []
    await list_files(folder_id="folder123")
    mock_client.list_files.assert_called_once_with(folder_id="folder123", page_size=25)


@pytest.mark.unit
async def test_search_files(mock_client):
    mock_client.search_files.return_value = [
        {"id": "f2", "name": "report.docx"},
    ]
    result = await search_files("report")
    assert len(result) == 1
    mock_client.search_files.assert_called_once_with("report", page_size=25)


@pytest.mark.unit
async def test_read_file(mock_client):
    mock_client.read_file.return_value = "Hello world"
    result = await read_file("f1")
    assert result == "Hello world"
    mock_client.read_file.assert_called_once_with("f1")


@pytest.mark.unit
async def test_create_file(mock_client):
    mock_client.create_file.return_value = {"id": "new1", "name": "new.doc"}
    result = await create_file(name="new.doc", mime_type="text/plain")
    assert result["id"] == "new1"
    mock_client.create_file.assert_called_once_with(
        name="new.doc",
        mime_type="text/plain",
        content=None,
        parent_folder_id=None,
    )


@pytest.mark.unit
async def test_update_file(mock_client):
    mock_client.update_file.return_value = {"id": "f1", "name": "renamed.doc"}
    result = await update_file(file_id="f1", name="renamed.doc")
    assert result["name"] == "renamed.doc"
    mock_client.update_file.assert_called_once_with("f1", name="renamed.doc", content=None)


@pytest.mark.unit
async def test_delete_file(mock_client):
    result = await delete_file("f1")
    assert result["status"] == "deleted"
    assert result["file_id"] == "f1"
    mock_client.delete_file.assert_called_once_with("f1")
