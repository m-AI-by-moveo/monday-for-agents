"""``mfa validate`` — validate agent YAML definitions."""

from __future__ import annotations

from pathlib import Path

import click

from a2a_server.cli_utils import error, header, info, success, suggestion, warning


def _validate_agent(yaml_path: Path) -> list[str]:
    """Validate a single agent YAML, returning a list of issues."""
    import yaml
    from pydantic import ValidationError

    from a2a_server.models import AgentDefinition

    issues: list[str] = []

    try:
        raw = yaml.safe_load(yaml_path.read_text())
    except yaml.YAMLError as exc:
        issues.append(f"YAML parse error: {exc}")
        return issues

    if not isinstance(raw, dict):
        issues.append("File does not contain a YAML mapping")
        return issues

    try:
        agent_def = AgentDefinition(**raw)
    except ValidationError as exc:
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err["loc"])
            issues.append(f"Schema error at {loc}: {err['msg']}")
        return issues

    # Semantic checks
    if not agent_def.prompt.system.strip():
        issues.append("System prompt is empty")

    port = agent_def.a2a.port
    if port < 1024 or port > 65535:
        issues.append(f"Port {port} is outside the recommended range (1024-65535)")

    if not agent_def.metadata.description:
        issues.append("Agent description is empty")

    return issues


@click.command("validate")
@click.option(
    "--agents-dir",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    required=True,
    help="Directory containing agent YAML files.",
)
def validate_command(agents_dir: str) -> None:
    """Validate agent YAML definitions."""
    agents_path = Path(agents_dir)
    yaml_files = sorted(agents_path.glob("*.yaml"))

    if not yaml_files:
        click.echo(error("No YAML files found in " + agents_dir))
        raise SystemExit(1)

    click.echo(header(f"Validating {len(yaml_files)} agent definition(s)...\n"))

    all_ports: dict[int, str] = {}
    total_issues = 0

    for yaml_path in yaml_files:
        agent_name = yaml_path.stem
        click.echo(info(f"  {agent_name}"))

        issues = _validate_agent(yaml_path)

        # Port collision check (best-effort: only if we parsed successfully)
        try:
            import yaml
            raw = yaml.safe_load(yaml_path.read_text())
            port = raw.get("a2a", {}).get("port")
            if port is not None:
                if port in all_ports:
                    issues.append(
                        f"Port {port} collides with agent '{all_ports[port]}'"
                    )
                else:
                    all_ports[port] = agent_name
        except Exception:
            pass

        if issues:
            total_issues += len(issues)
            for issue in issues:
                click.echo(f"    {warning(issue)}")
        else:
            click.echo(f"    {success('Valid')}")

    click.echo()
    if total_issues:
        click.echo(error(f"{total_issues} issue(s) found"))
        raise SystemExit(1)
    else:
        click.echo(success(f"All {len(yaml_files)} agent definition(s) are valid"))
