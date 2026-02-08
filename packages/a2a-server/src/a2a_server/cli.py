"""CLI entry-point for the Monday-for-Agents A2A server."""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Any

import click
from dotenv import load_dotenv

# Load .env from repo root (traverse up from this file)
_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent.parent.parent.parent
load_dotenv(_REPO_ROOT / ".env")
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from a2a_server.agent_loader import load_agent, load_all_agents
from a2a_server.claude_code_executor import ClaudeCodeExecutor
from a2a_server.health import health_routes, init_health
from a2a_server.logging_config import configure_logging
from a2a_server.mcp_config import build_mcp_config
from a2a_server.models import AgentDefinition
from a2a_server.registry import AgentRegistry
from a2a_server.server import create_a2a_app
from a2a_server.middleware import (
    APIKeyAuthMiddleware,
    InputValidationMiddleware,
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecureHeadersMiddleware,
)
from a2a_server.commands.doctor import doctor_command
from a2a_server.commands.status import status_command
from a2a_server.commands.validate import validate_command
from a2a_server.tracing import CorrelationMiddleware

logger = logging.getLogger(__name__)

# Default agents directory
_DEFAULT_AGENTS_DIR = _REPO_ROOT / "agents"


def _build_starlette_app(a2a_app: Any) -> Starlette:
    """Wrap an A2A app with health routes and middleware.

    The A2A SDK app is mounted as the root, while ``/health`` and
    ``/ready`` are added as additional routes.  Middleware is layered
    on top of the resulting Starlette application.
    """
    inner = a2a_app.build()
    app = Starlette(
        routes=[
            *health_routes,
            Mount("/", app=inner),
        ],
    )
    # Middleware stack (outermost first): SecureHeaders → SizeLimit →
    # RateLimit → Auth → Correlation → Validation
    # Note: add_middleware prepends, so we add in reverse order.
    app.add_middleware(InputValidationMiddleware)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(APIKeyAuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(SecureHeadersMiddleware)
    return app


# -----------------------------------------------------------------------
# CLI group
# -----------------------------------------------------------------------

@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.option("--json-logs", is_flag=True, help="Output structured JSON logs.")
def cli(verbose: bool, json_logs: bool) -> None:
    """Monday-for-Agents CLI."""
    configure_logging(verbose=verbose, json_format=json_logs)


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
        available = [p.stem for p in base_dir.glob("*.yaml")]
        msg = f"Agent file not found: {yaml_path}"
        if available:
            msg += f"\nAvailable agents: {', '.join(sorted(available))}"
        raise click.ClickException(msg)

    asyncio.run(_run_single(yaml_path))


async def _run_single(yaml_path: Path) -> None:
    """Load one agent and serve it."""
    agent_def = load_agent(yaml_path)

    # Build a minimal registry (the single agent can still be looked up)
    registry = AgentRegistry()
    registry.register(agent_def)
    agent_urls = {
        e.definition.metadata.name: e.url for e in registry.list_agents()
    }

    mcp_config = build_mcp_config(agent_def, agent_urls=agent_urls)
    executor = ClaudeCodeExecutor(agent_def=agent_def, mcp_config=mcp_config)
    a2a_app = create_a2a_app(agent_def, executor)

    starlette_app = _build_starlette_app(a2a_app)

    logger.info(
        "Starting agent '%s' on port %d",
        agent_def.metadata.name,
        agent_def.a2a.port,
    )

    init_health()

    config = uvicorn.Config(
        app=starlette_app,
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
    agent_urls = {
        e.definition.metadata.name: e.url for e in registry.list_agents()
    }

    servers: list[uvicorn.Server] = []

    for agent_def in definitions:
        mcp_config = build_mcp_config(agent_def, agent_urls=agent_urls)
        executor = ClaudeCodeExecutor(agent_def=agent_def, mcp_config=mcp_config)
        a2a_app = create_a2a_app(agent_def, executor)

        starlette_app = _build_starlette_app(a2a_app)

        config = uvicorn.Config(
            app=starlette_app,
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

    init_health()
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


# -----------------------------------------------------------------------
# Additional commands
# -----------------------------------------------------------------------

cli.add_command(validate_command)
cli.add_command(doctor_command)
cli.add_command(status_command)
