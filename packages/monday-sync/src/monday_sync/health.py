"""Agent health checks via A2A /health endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import httpx

from a2a_server.models import AgentDefinition

from monday_sync import monday_client

logger = logging.getLogger(__name__)

HEALTH_TIMEOUT = 5.0


@dataclass
class HealthResult:
    name: str
    port: int
    status: str  # healthy | unhealthy | not_running | error
    response_time_ms: float | None = None
    detail: str = ""


async def check_agent_health(agent: AgentDefinition) -> HealthResult:
    """GET http://localhost:{port}/health with a 5s timeout."""
    port = agent.a2a.port
    name = agent.metadata.name
    url = f"http://localhost:{port}/health"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=HEALTH_TIMEOUT)
        elapsed = (time.monotonic() - start) * 1000

        if resp.status_code == 200:
            return HealthResult(name=name, port=port, status="healthy", response_time_ms=elapsed)
        else:
            return HealthResult(
                name=name, port=port, status="unhealthy",
                response_time_ms=elapsed, detail=f"HTTP {resp.status_code}",
            )
    except httpx.ConnectError:
        return HealthResult(name=name, port=port, status="not_running", detail="Connection refused")
    except httpx.TimeoutException:
        elapsed = (time.monotonic() - start) * 1000
        return HealthResult(name=name, port=port, status="error", response_time_ms=elapsed, detail="Timeout")
    except Exception as e:
        return HealthResult(name=name, port=port, status="error", detail=str(e))


async def check_all_agents(agents: list[AgentDefinition]) -> list[HealthResult]:
    """Check health of all agents concurrently."""
    return await asyncio.gather(*(check_agent_health(a) for a in agents))


def print_results(results: list[HealthResult]) -> None:
    """Print health results to stdout."""
    status_colors = {
        "healthy": "\033[32m",      # green
        "unhealthy": "\033[33m",    # yellow
        "not_running": "\033[31m",  # red
        "error": "\033[31m",        # red
    }
    reset = "\033[0m"

    for r in results:
        color = status_colors.get(r.status, "")
        time_str = f"{r.response_time_ms:.0f}ms" if r.response_time_ms is not None else "-"
        detail = f" ({r.detail})" if r.detail else ""
        print(f"  {r.name:20s}  :{r.port}  {color}{r.status:12s}{reset}  {time_str}{detail}")


async def update_board_status(results: list[HealthResult], board_id: int) -> None:
    """Update the registry board Status column based on health results."""
    items = await monday_client.get_board_items(board_id)

    # Build name -> item_id mapping
    name_to_item: dict[str, str] = {}
    for item in items:
        for col in item.get("column_values", []):
            if col["id"] == "text" and col.get("text"):
                name_to_item[col["text"]] = item["id"]
                break
        else:
            name_to_item[item["name"]] = item["id"]

    for r in results:
        item_id = name_to_item.get(r.name)
        if not item_id:
            logger.warning("Agent '%s' not found on board %s", r.name, board_id)
            continue

        label = "Active" if r.status == "healthy" else "Down"
        value = json.dumps({"label": label})
        await monday_client.update_column_value(board_id, item_id, "status", value)
        logger.info("Updated board status for %s: %s", r.name, label)
