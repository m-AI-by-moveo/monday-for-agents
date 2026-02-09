"""FastMCP server exposing Google Calendar operations as MCP tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from google_calendar_mcp.tools.events import (
    list_events as _list_events,
    create_event as _create_event,
    update_event as _update_event,
    delete_event as _delete_event,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("google-calendar")

# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_calendar_events(
    calendar_id: str = "primary",
    time_range: str = "week",
    max_results: int = 25,
) -> str:
    """List upcoming events from a Google Calendar.

    Args:
        calendar_id: Calendar ID (default "primary").
        time_range: Time range to query. One of "today", "week", "month".
        max_results: Maximum number of events to return.
    """
    result = await _list_events(
        calendar_id=calendar_id,
        time_range=time_range,
        max_results=max_results,
    )
    return json.dumps(result)


@mcp.tool()
async def create_calendar_event(
    summary: str,
    start: str,
    end: str,
    calendar_id: str = "primary",
    description: str | None = None,
    location: str | None = None,
    attendees: str | None = None,
) -> str:
    """Create a new event on a Google Calendar.

    Args:
        summary: Event title / name.
        start: Start time in ISO 8601 format (e.g. "2025-06-01T09:00:00+03:00").
        end: End time in ISO 8601 format.
        calendar_id: Calendar ID (default "primary").
        description: Optional event description.
        location: Optional event location.
        attendees: Optional comma-separated list of attendee email addresses.
    """
    attendee_list = [e.strip() for e in attendees.split(",")] if attendees else None
    result = await _create_event(
        summary=summary,
        start=start,
        end=end,
        calendar_id=calendar_id,
        description=description,
        location=location,
        attendees=attendee_list,
    )
    return json.dumps(result)


@mcp.tool()
async def update_calendar_event(
    event_id: str,
    calendar_id: str = "primary",
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
) -> str:
    """Update an existing event on a Google Calendar.

    Args:
        event_id: The ID of the event to update.
        calendar_id: Calendar ID (default "primary").
        summary: New event title.
        start: New start time in ISO 8601 format.
        end: New end time in ISO 8601 format.
        description: New event description.
        location: New event location.
    """
    result = await _update_event(
        event_id=event_id,
        calendar_id=calendar_id,
        summary=summary,
        start=start,
        end=end,
        description=description,
        location=location,
    )
    return json.dumps(result)


@mcp.tool()
async def delete_calendar_event(
    event_id: str,
    calendar_id: str = "primary",
) -> str:
    """Delete an event from a Google Calendar.

    Args:
        event_id: The ID of the event to delete.
        calendar_id: Calendar ID (default "primary").
    """
    result = await _delete_event(event_id=event_id, calendar_id=calendar_id)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Google Calendar MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
