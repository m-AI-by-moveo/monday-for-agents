"""Google Calendar API client using service account authentication."""

from __future__ import annotations

import logging
import os
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarClient:
    """Wrapper around the Google Calendar v3 API using a service account."""

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
        self._service = build("calendar", "v3", credentials=credentials)
        logger.info("GoogleCalendarClient initialised with key file: %s", key_path)

    def list_events(
        self,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """List upcoming events from a calendar."""
        kwargs: dict[str, Any] = {
            "calendarId": calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_min:
            kwargs["timeMin"] = time_min
        if time_max:
            kwargs["timeMax"] = time_max

        result = self._service.events().list(**kwargs).execute()
        return result.get("items", [])

    def create_event(
        self,
        calendar_id: str = "primary",
        *,
        summary: str,
        start: str,
        end: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new calendar event."""
        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": e} for e in attendees]

        return self._service.events().insert(
            calendarId=calendar_id, body=body,
        ).execute()

    def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        **updates: Any,
    ) -> dict[str, Any]:
        """Update an existing calendar event."""
        existing = self._service.events().get(
            calendarId=calendar_id, eventId=event_id,
        ).execute()

        for key, value in updates.items():
            if key in ("start", "end"):
                existing[key] = {"dateTime": value}
            else:
                existing[key] = value

        return self._service.events().update(
            calendarId=calendar_id, eventId=event_id, body=existing,
        ).execute()

    def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
    ) -> None:
        """Delete a calendar event."""
        self._service.events().delete(
            calendarId=calendar_id, eventId=event_id,
        ).execute()


# Module-level singleton
_client: GoogleCalendarClient | None = None


def get_client() -> GoogleCalendarClient:
    """Return the module-level GoogleCalendarClient singleton."""
    global _client
    if _client is None:
        _client = GoogleCalendarClient()
    return _client
