"""Rich terminal dashboard combining health + Monday.com board data."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.table import Table

from a2a_server.agent_loader import load_all_agents

from monday_sync import monday_client
from monday_sync.health import check_all_agents

logger = logging.getLogger(__name__)

STATUS_STYLES = {
    "healthy": "green",
    "unhealthy": "yellow",
    "not_running": "red",
    "error": "red",
}


async def show_status(agents_dir: Path, board_id: int | None = None) -> None:
    """Show a combined status dashboard."""
    agents = load_all_agents(agents_dir)
    if not agents:
        Console().print("[yellow]No agents found.[/yellow]")
        return

    # Health checks
    health_results = await check_all_agents(agents)
    health_map = {r.name: r for r in health_results}

    # Board data (optional)
    board_agents: set[str] = set()
    if board_id:
        try:
            items = await monday_client.get_board_items(board_id)
            for item in items:
                for col in item.get("column_values", []):
                    if col["id"] == "text" and col.get("text"):
                        board_agents.add(col["text"])
                        break
                else:
                    board_agents.add(item["name"])
        except Exception as e:
            logger.warning("Could not fetch board data: %s", e)

    # Build table
    table = Table(title="Agent Status Dashboard")
    table.add_column("Agent", style="bold")
    table.add_column("Port", justify="right")
    table.add_column("Health")
    table.add_column("Response", justify="right")
    if board_id:
        table.add_column("On Board")

    any_down = False
    for agent in agents:
        name = agent.metadata.name
        hr = health_map.get(name)
        if not hr:
            continue

        style = STATUS_STYLES.get(hr.status, "")
        health_text = f"[{style}]{hr.status}[/{style}]"
        time_str = f"{hr.response_time_ms:.0f}ms" if hr.response_time_ms is not None else "-"

        row = [name, str(agent.a2a.port), health_text, time_str]
        if board_id:
            on_board = "[green]yes[/green]" if name in board_agents else "[red]no[/red]"
            row.append(on_board)

        table.add_row(*row)

        if hr.status != "healthy":
            any_down = True

    Console().print(table)

    if any_down:
        raise SystemExit(1)
