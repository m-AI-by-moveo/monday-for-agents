"""MCP tool functions for Google Calendar event operations."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google_calendar_mcp.client import get_client

logger = logging.getLogger(__name__)


async def list_events(
    calendar_id: str = "primary",
    time_range: str = "week",
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """List upcoming calendar events.

    Args:
        calendar_id: Calendar ID (default "primary").
        time_range: One of "today", "week", "month".
        max_results: Maximum number of events to return.

    Returns:
        List of event dicts.
    """
    client = get_client()
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()

    if time_range == "today":
        end = now.replace(hour=23, minute=59, second=59)
        time_max = end.isoformat()
    elif time_range == "month":
        time_max = (now + timedelta(days=30)).isoformat()
    else:  # week
        time_max = (now + timedelta(days=7)).isoformat()

    events = client.list_events(
        calendar_id=calendar_id,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
    )
    logger.info("Listed %d events from calendar %s", len(events), calendar_id)
    return events


async def create_event(
    summary: str,
    start: str,
    end: str,
    calendar_id: str = "primary",
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new calendar event.

    Args:
        summary: Event title.
        start: Start time in ISO 8601 format.
        end: End time in ISO 8601 format.
        calendar_id: Calendar ID (default "primary").
        description: Optional event description.
        location: Optional event location.
        attendees: Optional list of attendee email addresses.

    Returns:
        Created event dict.
    """
    client = get_client()
    event = client.create_event(
        calendar_id=calendar_id,
        summary=summary,
        start=start,
        end=end,
        description=description,
        location=location,
        attendees=attendees,
    )
    logger.info("Created event '%s' (id=%s)", summary, event.get("id"))
    return event


async def update_event(
    event_id: str,
    calendar_id: str = "primary",
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    """Update an existing calendar event.

    Args:
        event_id: The event ID to update.
        calendar_id: Calendar ID (default "primary").
        summary: New event title.
        start: New start time in ISO 8601 format.
        end: New end time in ISO 8601 format.
        description: New description.
        location: New location.

    Returns:
        Updated event dict.
    """
    client = get_client()
    updates: dict[str, Any] = {}
    if summary is not None:
        updates["summary"] = summary
    if start is not None:
        updates["start"] = start
    if end is not None:
        updates["end"] = end
    if description is not None:
        updates["description"] = description
    if location is not None:
        updates["location"] = location

    event = client.update_event(event_id, calendar_id=calendar_id, **updates)
    logger.info("Updated event %s", event_id)
    return event


async def delete_event(
    event_id: str,
    calendar_id: str = "primary",
) -> dict[str, str]:
    """Delete a calendar event.

    Args:
        event_id: The event ID to delete.
        calendar_id: Calendar ID (default "primary").

    Returns:
        Confirmation dict.
    """
    client = get_client()
    client.delete_event(event_id, calendar_id=calendar_id)
    logger.info("Deleted event %s from calendar %s", event_id, calendar_id)
    return {"status": "deleted", "event_id": event_id}
