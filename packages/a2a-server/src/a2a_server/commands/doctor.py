"""``mfa doctor`` — check system prerequisites and configuration."""

from __future__ import annotations

import os
import shutil
import socket
import sys

import click

from a2a_server.cli_utils import error, header, info, success, suggestion, warning

# Default agent ports to check
DEFAULT_PORTS = [10001, 10002, 10003, 10004]


def _check_python_version() -> tuple[bool, str]:
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 11):
        return True, f"Python {version_str}"
    return False, f"Python {version_str} (>= 3.11 required)"


def _check_env_var(name: str) -> tuple[bool, str]:
    val = os.environ.get(name, "")
    if val:
        # Mask the value for display
        masked = val[:4] + "..." if len(val) > 4 else "***"
        return True, f"{name} = {masked}"
    return False, f"{name} is not set"


def _check_tool(name: str) -> tuple[bool, str]:
    path = shutil.which(name)
    if path:
        return True, f"{name} found at {path}"
    return False, f"{name} not found in PATH"


def _check_port(port: int) -> tuple[bool, str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.bind(("127.0.0.1", port))
            return True, f"Port {port} is available"
    except OSError:
        return True, f"Port {port} is in use (agent may be running)"


def _check_agents_dir(agents_dir: str | None) -> tuple[bool, str]:
    from pathlib import Path

    if agents_dir:
        p = Path(agents_dir)
    else:
        # Try common locations
        for candidate in [Path("agents"), Path("../agents"), Path("../../agents")]:
            if candidate.is_dir():
                p = candidate
                break
        else:
            return False, "No agents directory found"

    yamls = list(p.glob("*.yaml"))
    if yamls:
        names = [y.stem for y in yamls]
        return True, f"Found {len(yamls)} agent(s): {', '.join(names)}"
    return False, f"No YAML files in {p}"


@click.command("doctor")
@click.option(
    "--agents-dir",
    type=click.Path(exists=False, file_okay=False, resolve_path=True),
    default=None,
    help="Directory containing agent YAML files.",
)
def doctor_command(agents_dir: str | None) -> None:
    """Check system prerequisites and configuration."""
    click.echo(header("MFA Doctor\n"))
    checks: list[tuple[str, list[tuple[bool, str]]]] = []

    # Python
    checks.append(("Python", [_check_python_version()]))

    # Environment variables
    env_checks = [
        _check_env_var("ANTHROPIC_API_KEY"),
        _check_env_var("MONDAY_API_TOKEN"),
        _check_env_var("MONDAY_BOARD_ID"),
    ]
    checks.append(("Environment Variables", env_checks))

    # CLI tools
    tool_checks = [
        _check_tool("node"),
        _check_tool("npm"),
        _check_tool("uv"),
    ]
    checks.append(("CLI Tools", tool_checks))

    # Ports
    port_checks = [_check_port(p) for p in DEFAULT_PORTS]
    checks.append(("Ports", port_checks))

    # Agent definitions
    checks.append(("Agent Definitions", [_check_agents_dir(agents_dir)]))

    has_issues = False
    for section_name, results in checks:
        click.echo(info(f"  {section_name}"))
        for ok, msg in results:
            if ok:
                click.echo(f"    {success(msg)}")
            else:
                click.echo(f"    {error(msg)}")
                has_issues = True
        click.echo()

    if has_issues:
        click.echo(warning("Some checks failed. See above for details."))
        click.echo(suggestion("Run 'mfa doctor' again after fixing issues"))
        raise SystemExit(1)
    else:
        click.echo(success("All checks passed!"))
