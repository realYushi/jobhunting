"""Environment loading for job-hunting tools."""

from __future__ import annotations

import os
from pathlib import Path

from .paths import project_root


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


def load_env(root: Path | None = None) -> None:
    """Load environment variables from .env file in project root.

    Handles: comments, blank lines, quoted values, inline comments, export prefix.
    Raises ConfigError if the .env file is missing.
    """
    root = root or project_root()
    env_path = root / ".env"
    if not env_path.exists():
        raise ConfigError(f"No .env file found at {env_path}")

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            if value.startswith('"') and '"' in value[1:]:
                value = value[1 : value.index('"', 1)]
            elif value.startswith("'") and "'" in value[1:]:
                value = value[1 : value.index("'", 1)]
            else:
                if " #" in value:
                    value = value[: value.index(" #")]
                elif " //" in value:
                    value = value[: value.index(" //")]

            os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    """Return an environment variable; raise ConfigError if missing or placeholder."""
    value = os.environ.get(name)
    if not value or value.startswith("your-"):
        raise ConfigError(f"{name} is not set or still has a placeholder value")
    return value


__all__ = ["ConfigError", "load_env", "require_env", "project_root"]
