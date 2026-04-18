"""``task-summoner config`` subcommands.

Surface area for user-level config (``docs_repo`` today). The heavy lifting —
resolution precedence, validation, persistence — lives in ``user_config``.
This module is a thin CLI layer that formats output and maps exceptions to
exit codes.
"""

from __future__ import annotations

import sys

from task_summoner.user_config import (
    ENV_VAR_BY_KEY,
    USER_CONFIG_KEYS,
    UserConfigError,
    resolve_all,
    resolve_user_config_value,
    set_value,
    unset_value,
    user_config_path,
)


def _format_resolved(key: str, value: str | None, source: str) -> str:
    display_value = value if value is not None else "(unset)"
    return f"{key} = {display_value}  [source: {source}]"


def cmd_config_get(key: str) -> int:
    """Print resolved value + source. Exit 0 if set, exit 1 if unset."""
    try:
        resolved = resolve_user_config_value(key)
    except UserConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(_format_resolved(resolved.key, resolved.value, resolved.source))
    return 0 if resolved.source != "unset" else 1


def cmd_config_set(key: str, value: str) -> int:
    """Validate and persist ``key=value`` to the user config file."""
    try:
        set_value(key, value)
    except UserConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    env_var = ENV_VAR_BY_KEY.get(key)
    print(f"Set {key} = {value}")
    print(f"  written to: {user_config_path()}")
    if env_var:
        print(f"  note: ${env_var} (if set) overrides this value at read time.")
    return 0


def cmd_config_unset(key: str) -> int:
    """Remove ``key`` from the user config file."""
    try:
        removed = unset_value(key)
    except UserConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if removed:
        print(f"Unset {key} (removed from {user_config_path()})")
    else:
        print(f"{key} was not set in {user_config_path()}")
    return 0


def cmd_config_list() -> int:
    """List all supported keys with their resolved value + source."""
    resolutions = resolve_all()
    if not resolutions:
        print("No config keys defined.")
        return 0

    print(f"# {user_config_path()}")
    for r in resolutions:
        print(_format_resolved(r.key, r.value, r.source))
    print()
    print("Environment overrides:")
    for key in USER_CONFIG_KEYS:
        env_var = ENV_VAR_BY_KEY.get(key)
        if env_var:
            print(f"  {key}: ${env_var}")
    return 0
