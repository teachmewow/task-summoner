"""User-level config — persisted at ``$XDG_CONFIG_HOME/task-summoner/config.json``.

This is distinct from the project-level ``config.yaml`` (provider credentials,
repo list, agent profiles). User config holds per-user preferences that skills
and state handlers need to discover at runtime — currently just ``docs_repo``,
the git repo where RFCs / decisions / c4s live.

Resolution precedence (highest first):

1. Environment variable (e.g. ``TASK_SUMMONER_DOCS_REPO``)
2. File (``$XDG_CONFIG_HOME/task-summoner/config.json``)
3. Unset

The resolver is the single source of truth — import
``resolve_user_config_value`` (or ``get_docs_repo``) from other modules rather
than re-implementing precedence handling.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from task_summoner.utils import atomic_write_json, safe_load_json

# Supported user-config keys. Additive: new keys go here + in ENV_VAR_BY_KEY.
USER_CONFIG_KEYS: tuple[str, ...] = ("docs_repo",)

ENV_VAR_BY_KEY: dict[str, str] = {
    "docs_repo": "TASK_SUMMONER_DOCS_REPO",
}

Source = Literal["env", "file", "unset"]


@dataclass(frozen=True)
class ResolvedValue:
    """A config value plus where it came from."""

    key: str
    value: str | None
    source: Source


class UserConfigError(ValueError):
    """Raised for user-facing validation errors. Message is actionable."""


def user_config_dir() -> Path:
    """Return the directory that holds ``config.json``.

    Honors ``XDG_CONFIG_HOME`` per the XDG Base Directory spec; defaults to
    ``~/.config`` when it is unset or empty.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "task-summoner"


def user_config_path() -> Path:
    """Full path to the user config file."""
    return user_config_dir() / "config.json"


def _load_file() -> dict[str, str]:
    """Load the file, returning an empty dict if missing or corrupt."""
    data = safe_load_json(user_config_path())
    if not isinstance(data, dict):
        return {}
    # Coerce to str-only values; silently drop non-string entries.
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def _save_file(data: dict[str, str]) -> None:
    atomic_write_json(user_config_path(), data)


def _require_known_key(key: str) -> None:
    if key not in USER_CONFIG_KEYS:
        raise UserConfigError(
            f"Unknown config key: {key!r}. Supported keys: {', '.join(USER_CONFIG_KEYS)}."
        )


def resolve_user_config_value(key: str) -> ResolvedValue:
    """Resolve a single key against env then file, returning its source."""
    _require_known_key(key)

    env_var = ENV_VAR_BY_KEY[key]
    env_value = os.environ.get(env_var)
    if env_value:
        return ResolvedValue(key=key, value=env_value, source="env")

    file_value = _load_file().get(key)
    if file_value:
        return ResolvedValue(key=key, value=file_value, source="file")

    return ResolvedValue(key=key, value=None, source="unset")


def resolve_all() -> list[ResolvedValue]:
    """Resolve every supported key in declaration order."""
    return [resolve_user_config_value(k) for k in USER_CONFIG_KEYS]


def get_docs_repo() -> str | None:
    """Convenience accessor for skills / state handlers.

    Returns the resolved ``docs_repo`` path or ``None`` when unset. Callers
    that need to know the source should use ``resolve_user_config_value``
    directly.
    """
    return resolve_user_config_value("docs_repo").value


# ---------------------------------------------------------------------------
# Mutations (only touch the file; env vars are the user's to manage)
# ---------------------------------------------------------------------------


def set_value(key: str, value: str) -> None:
    """Validate and persist ``key=value`` to the file."""
    _require_known_key(key)
    if key == "docs_repo":
        _validate_docs_repo(value)
    data = _load_file()
    data[key] = value
    _save_file(data)


def unset_value(key: str) -> bool:
    """Remove ``key`` from the file. Returns True if it was present."""
    _require_known_key(key)
    data = _load_file()
    if key not in data:
        return False
    del data[key]
    _save_file(data)
    return True


# ---------------------------------------------------------------------------
# Validation (docs_repo)
# ---------------------------------------------------------------------------

_DOCS_REPO_MARKER = Path(".task-summoner") / "config.yml"


def _validate_docs_repo(value: str) -> None:
    """Reject a ``docs_repo`` path that a skill can't actually use.

    Rules:
      1. Must be absolute (no ``~``, no relative paths).
      2. Must exist on disk and be a directory.
      3. Must be a git repo (``git rev-parse --show-toplevel`` succeeds).
      4. Must contain ``.task-summoner/config.yml`` (created by the
         task-summoner-docs-template fork, see ENG-93).
    """
    if not value:
        raise UserConfigError("docs_repo path cannot be empty.")

    path = Path(value)
    if not path.is_absolute():
        raise UserConfigError(
            f"docs_repo must be an absolute path, got {value!r}. Example: /Users/you/code/my-docs"
        )

    if not path.exists():
        raise UserConfigError(
            f"Path does not exist: {value}. "
            f"Clone the task-summoner-docs-template first, e.g.:\n"
            f"  gh repo create my-docs --template teachmewow/task-summoner-docs-template "
            f"--clone"
        )

    if not path.is_dir():
        raise UserConfigError(f"Path is not a directory: {value}.")

    if not _is_git_repo(path):
        raise UserConfigError(
            f"Path is not a git repo: {value}. "
            f"Clone the task-summoner-docs-template first, e.g.:\n"
            f"  gh repo create my-docs --template teachmewow/task-summoner-docs-template "
            f"--clone"
        )

    marker = path / _DOCS_REPO_MARKER
    if not marker.is_file():
        raise UserConfigError(
            f"Missing {_DOCS_REPO_MARKER} in {value}. "
            f"docs_repo must be a fork of task-summoner-docs-template (see ENG-93). "
            f"Create one with:\n"
            f"  gh repo create my-docs --template teachmewow/task-summoner-docs-template "
            f"--clone"
        )


def _is_git_repo(path: Path) -> bool:
    """True iff ``git -C <path> rev-parse --show-toplevel`` exits 0."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
