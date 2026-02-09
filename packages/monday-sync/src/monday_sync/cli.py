"""CLI entry point for monday-sync agent operations toolkit."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path

import click

logger = logging.getLogger(__name__)


def _find_repo_root() -> Path:
    """Find the repository root by looking for pyproject.toml."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def _default_agents_dir() -> Path:
    return _find_repo_root() / "agents"


@click.group()
@click.option("--verbose", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """monday-sync — Agent operations toolkit for Monday.com."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )

    # Load .env from repo root
    try:
        from dotenv import load_dotenv
        load_dotenv(_find_repo_root() / ".env")
    except ImportError:
        pass


@cli.command()
@click.option(
    "--agents-dir",
    type=click.Path(exists=True, path_type=Path),
    default=_default_agents_dir,
    help="Path to agents YAML directory",
)
@click.option(
    "--board-id",
    type=int,
    envvar="MONDAY_REGISTRY_BOARD_ID",
    required=True,
    help="Monday.com registry board ID",
)
def sync(agents_dir: Path, board_id: int) -> None:
    """Sync agent YAML definitions to Monday.com registry board."""
    from monday_sync.sync import sync_agents

    asyncio.run(sync_agents(agents_dir, board_id))


@cli.command()
@click.option("--workspace-id", type=int, default=None, help="Monday.com workspace ID")
def setup(workspace_id: int | None) -> None:
    """Create Monday.com boards (Tasks + Registry) with correct schema."""
    from monday_sync.board_setup import create_tasks_board, setup_registry_board

    async def _setup() -> None:
        tasks_board = await create_tasks_board(workspace_id)
        registry_board = await setup_registry_board(workspace_id)
        click.echo(f"Tasks board ID: {tasks_board['id']}")
        click.echo(f"Registry board ID: {registry_board['id']}")
        click.echo("\nAdd these to your .env file:")
        click.echo(f"MONDAY_BOARD_ID={tasks_board['id']}")
        click.echo(f"MONDAY_REGISTRY_BOARD_ID={registry_board['id']}")

    asyncio.run(_setup())


@cli.command()
@click.option(
    "--agents-dir",
    type=click.Path(exists=True, path_type=Path),
    default=_default_agents_dir,
    help="Path to agents YAML directory",
)
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
def validate(agents_dir: Path, strict: bool) -> None:
    """Validate agent YAML definitions."""
    from monday_sync.validate import validate_all

    report = validate_all(agents_dir)
    report.print()

    if report.has_errors or (strict and report.has_warnings):
        raise SystemExit(1)


@cli.command()
@click.option(
    "--agents-dir",
    type=click.Path(exists=True, path_type=Path),
    default=_default_agents_dir,
    help="Path to agents YAML directory",
)
@click.option(
    "--update-board",
    is_flag=True,
    help="Update registry board Status column with health results",
)
@click.option(
    "--board-id",
    type=int,
    envvar="MONDAY_REGISTRY_BOARD_ID",
    default=None,
    help="Monday.com registry board ID (required with --update-board)",
)
def health(agents_dir: Path, update_board: bool, board_id: int | None) -> None:
    """Check health of running agents."""
    from monday_sync.health import check_all_agents, print_results, update_board_status

    from a2a_server.agent_loader import load_all_agents

    agents = load_all_agents(agents_dir)
    if not agents:
        click.echo("No agents found.")
        raise SystemExit(1)

    results = asyncio.run(check_all_agents(agents))
    print_results(results)

    if update_board:
        if not board_id:
            click.echo("Error: --board-id required with --update-board")
            raise SystemExit(1)
        asyncio.run(update_board_status(results, board_id))

    if any(r.status != "healthy" for r in results):
        raise SystemExit(1)


@cli.command()
@click.option(
    "--agents-dir",
    type=click.Path(exists=True, path_type=Path),
    default=_default_agents_dir,
    help="Path to agents YAML directory",
)
@click.option(
    "--board-id",
    type=int,
    envvar="MONDAY_REGISTRY_BOARD_ID",
    default=None,
    help="Monday.com registry board ID",
)
def status(agents_dir: Path, board_id: int | None) -> None:
    """Show agent status dashboard."""
    from monday_sync.status import show_status

    asyncio.run(show_status(agents_dir, board_id))


@cli.command()
@click.option(
    "--agents-dir",
    type=click.Path(exists=True, path_type=Path),
    default=_default_agents_dir,
    help="Path to agents YAML directory",
)
@click.option(
    "--board-id",
    type=int,
    envvar="MONDAY_REGISTRY_BOARD_ID",
    required=True,
    help="Monday.com registry board ID",
)
def watch(agents_dir: Path, board_id: int) -> None:
    """Watch agent YAMLs and auto-sync on change."""
    from monday_sync.watch import watch_and_sync

    asyncio.run(watch_and_sync(agents_dir, board_id))


@cli.command()
def pull() -> None:
    """Pull agent definitions from Monday.com board (not yet implemented)."""
    click.echo("pull is not yet implemented. Use 'sync' to push YAML -> Monday.com.")
    raise SystemExit(0)
