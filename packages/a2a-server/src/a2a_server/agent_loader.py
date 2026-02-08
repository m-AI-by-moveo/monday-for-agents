"""Load agent definitions from YAML files with environment variable expansion."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from a2a_server.models import AgentDefinition

logger = logging.getLogger(__name__)

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def expand_env_vars(value: Any) -> Any:
    """Recursively expand ``${VAR_NAME}`` patterns in strings, lists, and dicts.

    Missing environment variables are replaced with an empty string and a
    warning is logged.
    """
    if isinstance(value, str):
        def _replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value is None:
                logger.warning("Environment variable %s is not set", var_name)
                return ""
            return env_value

        return _ENV_VAR_PATTERN.sub(_replacer, value)

    if isinstance(value, dict):
        return {k: expand_env_vars(v) for k, v in value.items()}

    if isinstance(value, list):
        return [expand_env_vars(item) for item in value]

    return value


def load_agent(path: Path) -> AgentDefinition:
    """Read a single agent YAML file, expand env vars, and validate.

    Args:
        path: Path to the ``.yaml`` agent definition file.

    Returns:
        A validated :class:`AgentDefinition`.

    Raises:
        FileNotFoundError: If *path* does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        pydantic.ValidationError: If the expanded data does not conform to
            the schema.
    """
    logger.info("Loading agent definition from %s", path)
    if not path.exists():
        raise FileNotFoundError(f"Agent definition not found: {path}")

    raw_text = path.read_text(encoding="utf-8")
    raw_data = yaml.safe_load(raw_text)

    if raw_data is None:
        raise ValueError(f"Agent definition file is empty: {path}")

    expanded = expand_env_vars(raw_data)
    agent_def = AgentDefinition.model_validate(expanded)
    logger.info(
        "Loaded agent '%s' (version %s)",
        agent_def.metadata.name,
        agent_def.metadata.version,
    )
    return agent_def


def load_all_agents(agents_dir: Path) -> list[AgentDefinition]:
    """Load every ``.yaml`` file in *agents_dir* as an agent definition.

    Files that fail to parse are logged and skipped so that one broken
    definition does not prevent the rest from loading.

    Args:
        agents_dir: Directory containing agent YAML files.

    Returns:
        List of successfully loaded :class:`AgentDefinition` instances.
    """
    if not agents_dir.is_dir():
        raise FileNotFoundError(f"Agents directory not found: {agents_dir}")

    yaml_files = sorted(agents_dir.glob("*.yaml"))
    if not yaml_files:
        logger.warning("No .yaml files found in %s", agents_dir)
        return []

    definitions: list[AgentDefinition] = []
    for yaml_file in yaml_files:
        try:
            definitions.append(load_agent(yaml_file))
        except Exception:
            logger.exception("Failed to load agent from %s", yaml_file)

    logger.info(
        "Loaded %d/%d agent definitions from %s",
        len(definitions),
        len(yaml_files),
        agents_dir,
    )
    return definitions
