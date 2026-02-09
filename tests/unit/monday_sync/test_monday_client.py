"""Tests for monday_sync.monday_client."""

from __future__ import annotations

import httpx
import pytest
import respx

from monday_sync.monday_client import get_headers, graphql


@pytest.mark.unit
class TestGetHeaders:
    """Tests for get_headers()."""

    def test_returns_headers(self) -> None:
        """Headers include Authorization from env."""
        headers = get_headers()
        assert headers["Authorization"] == "test-token-do-not-use"
        assert headers["Content-Type"] == "application/json"

    def test_missing_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises ValueError when MONDAY_API_TOKEN is not set."""
        monkeypatch.delenv("MONDAY_API_TOKEN")
        with pytest.raises(ValueError, match="MONDAY_API_TOKEN"):
            get_headers()


@pytest.mark.unit
class TestGraphQL:
    """Tests for graphql()."""

    @respx.mock
    async def test_successful_query(self) -> None:
        """Successful query returns parsed JSON."""
        respx.post("https://api.monday.com/v2").mock(
            return_value=httpx.Response(200, json={
                "data": {"boards": [{"id": "123"}]}
            })
        )
        result = await graphql("query { boards { id } }")
        assert result["data"]["boards"][0]["id"] == "123"

    @respx.mock
    async def test_api_error(self) -> None:
        """GraphQL errors raise RuntimeError."""
        respx.post("https://api.monday.com/v2").mock(
            return_value=httpx.Response(200, json={
                "errors": [{"message": "Invalid query"}]
            })
        )
        with pytest.raises(RuntimeError, match="Monday.com API error"):
            await graphql("query { bad }")

    @respx.mock
    async def test_http_error(self) -> None:
        """Non-200 HTTP status raises."""
        respx.post("https://api.monday.com/v2").mock(
            return_value=httpx.Response(500, text="Server Error")
        )
        with pytest.raises(httpx.HTTPStatusError):
            await graphql("query { boards { id } }")
