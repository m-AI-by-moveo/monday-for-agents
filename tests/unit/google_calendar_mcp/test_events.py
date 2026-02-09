"""Tests for Google Calendar MCP event tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from google_calendar_mcp.tools.events import (
    list_events,
    create_event,
    update_event,
    delete_event,
)


@pytest.fixture
def mock_client():
    """Fixture providing a mocked GoogleCalendarClient."""
    client = MagicMock()
    with patch("google_calendar_mcp.tools.events.get_client", return_value=client):
        yield client


@pytest.mark.unit
async def test_list_events_returns_items(mock_client):
    mock_client.list_events.return_value = [
        {"id": "e1", "summary": "Standup", "start": {"dateTime": "2025-01-01T09:00:00Z"}},
        {"id": "e2", "summary": "Retro", "start": {"dateTime": "2025-01-01T14:00:00Z"}},
    ]
    result = await list_events(time_range="today")
    assert len(result) == 2
    assert result[0]["summary"] == "Standup"
    mock_client.list_events.assert_called_once()


@pytest.mark.unit
async def test_list_events_week_range(mock_client):
    mock_client.list_events.return_value = []
    result = await list_events(time_range="week")
    assert result == []
    call_kwargs = mock_client.list_events.call_args
    assert call_kwargs.kwargs.get("time_max") is not None


@pytest.mark.unit
async def test_create_event(mock_client):
    mock_client.create_event.return_value = {
        "id": "new1",
        "summary": "Planning",
        "start": {"dateTime": "2025-01-02T10:00:00Z"},
    }
    result = await create_event(
        summary="Planning",
        start="2025-01-02T10:00:00Z",
        end="2025-01-02T11:00:00Z",
    )
    assert result["id"] == "new1"
    mock_client.create_event.assert_called_once_with(
        calendar_id="primary",
        summary="Planning",
        start="2025-01-02T10:00:00Z",
        end="2025-01-02T11:00:00Z",
        description=None,
        location=None,
        attendees=None,
    )


@pytest.mark.unit
async def test_create_event_with_attendees(mock_client):
    mock_client.create_event.return_value = {"id": "new2", "summary": "Meeting"}
    result = await create_event(
        summary="Meeting",
        start="2025-01-02T10:00:00Z",
        end="2025-01-02T11:00:00Z",
        attendees=["alice@example.com", "bob@example.com"],
    )
    assert result["id"] == "new2"
    call_kwargs = mock_client.create_event.call_args
    assert call_kwargs.kwargs["attendees"] == ["alice@example.com", "bob@example.com"]


@pytest.mark.unit
async def test_update_event(mock_client):
    mock_client.update_event.return_value = {"id": "e1", "summary": "Updated"}
    result = await update_event(event_id="e1", summary="Updated")
    assert result["summary"] == "Updated"
    mock_client.update_event.assert_called_once()


@pytest.mark.unit
async def test_delete_event(mock_client):
    result = await delete_event(event_id="e1")
    assert result["status"] == "deleted"
    assert result["event_id"] == "e1"
    mock_client.delete_event.assert_called_once_with("e1", calendar_id="primary")
