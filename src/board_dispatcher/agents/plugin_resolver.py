"""Plugin resolution strategy — decides how agents load the aiops-workflows plugin.

Two modes:
- INSTALLED: Plugin is already installed in the user's Claude Code setup.
  Agents inherit it via setting_sources=["user"]. No explicit injection needed.
- LOCAL: Plugin is loaded from a local directory path.
  Used when the user hasn't installed the plugin globally (e.g., evaluators, CI).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import structlog

log = structlog.get_logger()


class PluginMode(str, Enum):
    """How the aiops-workflows plugin is provided to agents."""

    INSTALLED = "installed"
    LOCAL = "local"


class PluginResolver:
    """Resolves the plugin list for agent options based on configured mode.

    Strategy pattern: the resolver encapsulates the decision of how plugins
    are provided, keeping AgentOptionsFactory agnostic to the source.
    """

    def __init__(self, mode: PluginMode, plugin_path: str = "") -> None:
        self._mode = mode
        self._plugin_path = plugin_path

    @property
    def mode(self) -> PluginMode:
        return self._mode

    def resolve(self) -> list[dict]:
        """Return the plugins list for ClaudeAgentOptions.

        - INSTALLED mode: empty list (plugin comes from user settings).
        - LOCAL mode: list with one local plugin entry.
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
