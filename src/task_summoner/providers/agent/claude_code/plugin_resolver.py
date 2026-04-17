"""Plugin resolution strategy — decides how the tmw-workflows plugin is loaded.

Two modes:
- INSTALLED: plugin is already registered in the user's Claude Code setup.
  Agents inherit it via `setting_sources=["user"]`. No explicit injection needed.
- LOCAL: plugin is loaded from a local directory path. Used when the user hasn't
  installed the plugin globally (evaluators, CI, development).

Lives alongside the Claude Code adapter because the plugin contract is specific
to Claude Code's `ClaudeAgentOptions.plugins` shape. Other agent providers (e.g.
Codex) define their own plugin conventions if/when they gain plugin support.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import structlog

log = structlog.get_logger()


class PluginMode(str, Enum):
    """How the tmw-workflows plugin is provided to Claude Code agents."""

    INSTALLED = "installed"
    LOCAL = "local"


class PluginResolver:
    """Resolves the plugin list for `ClaudeAgentOptions` based on the configured mode."""

    def __init__(self, mode: PluginMode, plugin_path: str = "") -> None:
        self._mode = mode
        self._plugin_path = plugin_path

    @property
    def mode(self) -> PluginMode:
        return self._mode

    def resolve(self) -> list[dict[str, str]]:
        """Return the plugins list for `ClaudeAgentOptions`.

        - INSTALLED: empty list (plugin comes from user settings).
        - LOCAL: one entry pointing at `plugin_path`.
        """
        if self._mode == PluginMode.INSTALLED:
            log.debug("Plugin mode: installed — relying on user settings")
            return []

        resolved = str(Path(self._plugin_path).resolve())
        log.debug("Plugin mode: local", path=resolved)
        return [{"type": "local", "path": resolved}]

    def validate(self) -> list[str]:
        """Return validation errors for the current configuration."""
        if self._mode == PluginMode.LOCAL:
            if not self._plugin_path:
                return ["plugin_mode is 'local' but plugin_path is not set"]
            if not Path(self._plugin_path).is_dir():
                return [f"plugin_path does not exist: {self._plugin_path}"]
        return []
