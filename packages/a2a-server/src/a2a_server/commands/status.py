"""``mfa status`` — show health status of running agents."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
import httpx

from a2a_server.cli_utils import error, header, info, success, warning


async def _check_agent_health(name: str, port: int) -> dict:
    """Hit /health on a single agent, return status info."""
    url = f"http://localhost:{port}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "name": name,
                    "port": port,
                    "status": "healthy",
                    "uptime": data.get("uptime_seconds", "?"),
                }
            return {
                "name": name,
                "port": port,
                "status": "unhealthy",
                "detail": f"HTTP {resp.status_code}",
            }
    except httpx.ConnectError:
        return {"name": name, "port": port, "status": "not_running"}
    except Exception as exc:
        return {"name": name, "port": port, "status": "error", "detail": str(exc)}


async def _check_all(agents: list[tuple[str, int]]) -> list[dict]:
    tasks = [_check_agent_health(name, port) for name, port in agents]
    return await asyncio.gather(*tasks)


@click.command("status")
@click.option(
    "--agents-dir",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    required=True,
    help="Directory containing agent YAML files.",
)
def status_command(agents_dir: str) -> None:
    """Show health status of running agents."""
    import yaml

    agents_path = Path(agents_dir)
    yaml_files = sorted(agents_path.glob("*.yaml"))

    if not yaml_files:
        click.echo(error("No YAML files found in " + agents_dir))
        raise SystemExit(1)

    agents: list[tuple[str, int]] = []
    for yf in yaml_files:
        try:
            raw = yaml.safe_load(yf.read_text())
            port = raw.get("a2a", {}).get("port", 10000)
            agents.append((yf.stem, port))
        except Exception:
            agents.append((yf.stem, 0))

    click.echo(header("Agent Status\n"))

    results = asyncio.run(_check_all(agents))

    for r in results:
        name = r["name"]
        port = r["port"]
        status = r["status"]

        if status == "healthy":
            uptime = r.get("uptime", "?")
            click.echo(f"  {success(f'{name} (:{port})')}")
            click.echo(f"    Uptime: {uptime}s")
        elif status == "unhealthy":
            detail = r.get("detail", "")
            click.echo(f"  {warning(f'{name} (:{port}) — unhealthy: {detail}')}")
        elif status == "not_running":
            click.echo(f"  {error(f'{name} (:{port}) — not running')}")
        else:
            detail = r.get("detail", "")
            click.echo(f"  {error(f'{name} (:{port}) — error: {detail}')}")

    click.echo()
