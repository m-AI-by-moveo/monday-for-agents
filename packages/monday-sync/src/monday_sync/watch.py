"""File watcher with auto-validate and auto-sync on YAML changes."""

from __future__ import annotations

import logging
from pathlib import Path

import click
from watchfiles import Change, awatch

from monday_sync.sync import sync_agents
from monday_sync.validate import Severity, validate_all

logger = logging.getLogger(__name__)

CHANGE_LABELS = {
    Change.added: "added",
    Change.modified: "modified",
    Change.deleted: "deleted",
}


async def watch_and_sync(agents_dir: Path, board_id: int) -> None:
    """Watch agents directory for YAML changes. Validate then sync."""
    click.echo(f"Watching {agents_dir} for changes... (Ctrl+C to stop)")

    try:
        async for changes in awatch(agents_dir, watch_filter=_yaml_filter):
            for change_type, path_str in changes:
                label = CHANGE_LABELS.get(change_type, str(change_type))
                fname = Path(path_str).name
                click.echo(f"\n  {label}: {fname}")

            # Validate first
            report = validate_all(agents_dir)
            if report.has_errors:
                click.echo("  Validation errors found — skipping sync:")
                report.print()
                continue

            if report.has_warnings:
                click.echo("  Warnings:")
                report.print()

            # Sync
            click.echo("  Syncing to Monday.com...")
            try:
                await sync_agents(agents_dir, board_id)
                click.echo("  Sync complete.")
            except Exception as e:
                click.echo(f"  Sync failed: {e}")

    except KeyboardInterrupt:
        click.echo("\nStopped.")


def _yaml_filter(change: Change, path: str) -> bool:
    """Only watch .yaml files."""
    return path.endswith(".yaml")
