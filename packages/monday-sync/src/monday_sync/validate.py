"""YAML validation for agent definitions with severity levels."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml
from pydantic import ValidationError

from a2a_server.models import AgentDefinition

logger = logging.getLogger(__name__)

# Known builtin MCP sources from the workspace packages
KNOWN_BUILTIN_SOURCES = {
    "builtin:monday-mcp",
    "builtin:google-calendar-mcp",
    "builtin:google-drive-mcp",
}

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass
class ValidationIssue:
    file: str
    severity: Severity
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    def add(self, file: str, severity: Severity, message: str) -> None:
        self.issues.append(ValidationIssue(file=file, severity=severity, message=message))

    def print(self) -> None:
        """Print the validation report to stdout."""
        if not self.issues:
            print("All agent definitions are valid.")
            return

        for issue in self.issues:
            marker = "\033[31mERROR\033[0m" if issue.severity == Severity.ERROR else "\033[33mWARN\033[0m"
            print(f"  {marker}  {issue.file}: {issue.message}")

        print(f"\n{self.error_count} error(s), {self.warning_count} warning(s)")


def _find_env_refs(data: object) -> list[str]:
    """Recursively find all ${VAR} references in a raw YAML data structure."""
    refs: list[str] = []
    if isinstance(data, str):
        refs.extend(_ENV_VAR_PATTERN.findall(data))
    elif isinstance(data, dict):
        for v in data.values():
            refs.extend(_find_env_refs(v))
    elif isinstance(data, list):
        for item in data:
            refs.extend(_find_env_refs(item))
    return refs


def validate_all(agents_dir: Path) -> ValidationReport:
    """Validate all agent YAML files in a directory.

    Returns a ValidationReport with all issues found. This is a pure
    function suitable for reuse from the watch module.
    """
    report = ValidationReport()

    if not agents_dir.is_dir():
        report.add(str(agents_dir), Severity.ERROR, "Directory does not exist")
        return report

    yaml_files = sorted(agents_dir.glob("*.yaml"))
    if not yaml_files:
        report.add(str(agents_dir), Severity.WARNING, "No YAML files found")
        return report

    seen_names: dict[str, str] = {}  # name -> filename
    seen_ports: dict[int, str] = {}  # port -> filename

    for path in yaml_files:
        fname = path.name

        # 1. YAML parse
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            report.add(fname, Severity.ERROR, f"YAML parse error: {e}")
            continue

        if raw is None:
            report.add(fname, Severity.ERROR, "File is empty")
            continue

        # 2. Env var references
        env_refs = _find_env_refs(raw)
        for var in env_refs:
            if os.environ.get(var) is None:
                report.add(fname, Severity.WARNING, f"Environment variable ${{{var}}} is not set")

        # 3. Pydantic schema validation
        try:
            agent = AgentDefinition.model_validate(raw)
        except ValidationError as e:
            for err in e.errors():
                loc = " -> ".join(str(x) for x in err["loc"])
                report.add(fname, Severity.ERROR, f"Schema error at {loc}: {err['msg']}")
            continue

        name = agent.metadata.name

        # 4. Duplicate names
        if name in seen_names:
            report.add(
                fname, Severity.ERROR,
                f"Duplicate agent name '{name}' (also in {seen_names[name]})",
            )
        else:
            seen_names[name] = fname

        # 5. Port range
        port = agent.a2a.port
        if port < 1024 or port > 65535:
            report.add(fname, Severity.ERROR, f"Port {port} outside valid range 1024-65535")

        # 6. Port conflicts
        if port in seen_ports:
            report.add(
                fname, Severity.ERROR,
                f"Port {port} conflicts with {seen_ports[port]}",
            )
        else:
            seen_ports[port] = fname

        # 7. Unknown MCP sources
        for server in agent.tools.mcp_servers:
            if server.source.startswith("builtin:") and server.source not in KNOWN_BUILTIN_SOURCES:
                report.add(fname, Severity.ERROR, f"Unknown builtin MCP source: {server.source}")

        # 8. Empty system prompt
        if not agent.prompt.system.strip():
            report.add(fname, Severity.WARNING, "Empty system prompt")

        # 9. No A2A skills
        if not agent.a2a.skills:
            report.add(fname, Severity.WARNING, "No A2A skills defined")

    return report
