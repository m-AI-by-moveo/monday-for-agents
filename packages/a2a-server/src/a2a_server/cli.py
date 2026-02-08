"""CLI entry-point for the Monday-for-Agents A2A server."""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Any

import click
import uvicorn

from a2a_server.agent_executor import LangGraphA2AExecutor
from a2a_server.agent_loader import load_agent, load_all_agents
from a2a_server.graph import build_graph
from a2a_server.models import AgentDefinition
from a2a_server.registry import AgentRegistry, make_a2a_send_tool
from a2a_server.server import create_a2a_app

logger = logging.getLogger(__name__)

# Default agents directory relative to the package root:
# packages/a2a-server/src/a2a_server/../../../../../../agents  ->  <repo>/agents
_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_AGENTS_DIR = _PACKAGE_DIR.parent.parent.parent.parent / "agents"


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# -----------------------------------------------------------------------
# CLI group
# -----------------------------------------------------------------------

@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def cli(verbose: bool) -> None:
    """Monday-for-Agents CLI."""
    _configure_logging(verbose)


# -----------------------------------------------------------------------
# mfa run <agent-name>
# -----------------------------------------------------------------------

@cli.command()
@click.argument("agent_name")
@click.option(
    "--agents-dir",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=None,
    help="Directory containing agent YAML files.",
)
def run(agent_name: str, agents_dir: str | None) -> None:
    """Run a single agent A2A server."""
    base_dir = Path(agents_dir) if agents_dir else _DEFAULT_AGENTS_DIR
    yaml_path = base_dir / f"{agent_name}.yaml"

    if not yaml_path.exists():
        raise click.ClickException(f"Agent file not found: {yaml_path}")

    asyncio.run(_run_single(yaml_path))


async def _run_single(yaml_path: Path) -> None:
    """Load one agent and serve it."""
    agent_def = load_agent(yaml_path)

    # Build a minimal registry (the single agent can still be looked up)
    registry = AgentRegistry()
    registry.register(agent_def)
    send_tool = make_a2a_send_tool(registry)

    graph = await build_graph(agent_def, extra_tools=[send_tool])
    executor = LangGraphA2AExecutor(graph=graph, agent_def=agent_def)
    a2a_app = create_a2a_app(agent_def, executor)

    logger.info(
        "Starting agent '%s' on port %d",
        agent_def.metadata.name,
        agent_def.a2a.port,
    )

    config = uvicorn.Config(
        app=a2a_app.build(),
        host="0.0.0.0",
        port=agent_def.a2a.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


# -----------------------------------------------------------------------
# mfa run-all
# -----------------------------------------------------------------------

@cli.command("run-all")
@click.option(
    "--agents-dir",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=None,
    help="Directory containing agent YAML files.",
)
def run_all(agents_dir: str | None) -> None:
    """Run all agents concurrently."""
    base_dir = Path(agents_dir) if agents_dir else _DEFAULT_AGENTS_DIR
    asyncio.run(_run_all(base_dir))


async def _run_all(agents_dir: Path) -> None:
    """Load every agent YAML and run all A2A servers concurrently."""
    definitions = load_all_agents(agents_dir)
    if not definitions:
        logger.error("No agent definitions found in %s", agents_dir)
        return

    # Shared registry so agents can message each other
    registry = AgentRegistry.from_definitions(definitions)
    send_tool = make_a2a_send_tool(registry)

    servers: list[uvicorn.Server] = []

    for agent_def in definitions:
        graph = await build_graph(agent_def, extra_tools=[send_tool])
        executor = LangGraphA2AExecutor(graph=graph, agent_def=agent_def)
        a2a_app = create_a2a_app(agent_def, executor)

        config = uvicorn.Config(
            app=a2a_app.build(),
            host="0.0.0.0",
            port=agent_def.a2a.port,
            log_level="info",
        )
        servers.append(uvicorn.Server(config))

        logger.info(
            "Prepared agent '%s' on port %d",
            agent_def.metadata.name,
            agent_def.a2a.port,
        )

    logger.info("Starting %d agent server(s) concurrently", len(servers))

    # Run all servers as concurrent tasks; cancel everything on first
    # failure or SIGINT/SIGTERM.
    tasks = [asyncio.create_task(_serve(s)) for s in servers]

    # Graceful shutdown on signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: _cancel_all(tasks))

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    # If one crashes, cancel the rest
    for task in pending:
        task.cancel()

    # Re-raise the first exception (if any)
    for task in done:
        exc = task.exception()
        if exc is not None:
            raise exc


async def _serve(server: uvicorn.Server) -> None:
    await server.serve()


def _cancel_all(tasks: list[asyncio.Task[Any]]) -> None:
    for task in tasks:
        task.cancel()
