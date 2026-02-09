"""Tests for monday_sync.sync."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from monday_sync.sync import sync_agents


def _write_agent_yaml(agents_dir: Path, name: str, port: int) -> None:
    (agents_dir / f"{name}.yaml").write_text(
        f"""\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: {name}
  display_name: "{name.title()}"
  description: "Test agent"
  version: "1.0.0"
a2a:
  port: {port}
  skills:
    - id: s1
      name: S
      description: S
prompt:
  system: "test"
"""
    )


@pytest.mark.unit
class TestSyncAgents:
    """Tests for sync_agents()."""

    @respx.mock
    async def test_creates_new_agents(self, tmp_path: Path) -> None:
        """New agents are created on the board."""
        _write_agent_yaml(tmp_path, "new-agent", 10050)

        # Mock get_board_items (empty board)
        respx.post("https://api.monday.com/v2").mock(
            side_effect=[
                # First call: get_board_items query
                httpx.Response(200, json={
                    "data": {"boards": [{"items_page": {"items": []}}]}
                }),
                # Second call: create_item mutation
                httpx.Response(200, json={
                    "data": {"create_item": {"id": "999"}}
                }),
            ]
        )

        await sync_agents(tmp_path, 12345)

    @respx.mock
    async def test_updates_existing_agents(self, tmp_path: Path) -> None:
        """Existing agents are updated, not re-created."""
        _write_agent_yaml(tmp_path, "existing-agent", 10051)

        respx.post("https://api.monday.com/v2").mock(
            side_effect=[
                # First call: get_board_items (agent already exists)
                httpx.Response(200, json={
                    "data": {"boards": [{
                        "items_page": {"items": [{
                            "id": "888",
                            "name": "Existing Agent",
                            "column_values": [{"id": "text", "text": "existing-agent"}],
                        }]}
                    }]}
                }),
                # Second call: change_multiple_column_values mutation
                httpx.Response(200, json={
                    "data": {"change_multiple_column_values": {"id": "888"}}
                }),
            ]
        )

        await sync_agents(tmp_path, 12345)

    async def test_skips_on_no_yamls(self, tmp_path: Path) -> None:
        """No YAML files -> logs warning and returns."""
        # Should not raise or make API calls
        await sync_agents(tmp_path, 12345)
