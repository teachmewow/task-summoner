"""Shared agent options factory — all agents inherit from this base config.

Ensures every spawned agent gets:
- User settings (installed plugins, authenticated MCP servers)
- The aiops-workflows plugin (via installed settings or explicit local path)
- bypassPermissions for headless execution
- .env variables forwarded
"""

from __future__ import annotations

import os

from claude_agent_sdk import ClaudeAgentOptions

from task_summoner.config import AgentConfig, TaskSummonerConfig

from .plugin_resolver import PluginResolver


class AgentOptionsFactory:
    """Builds ClaudeAgentOptions with shared base config.

    All agents get the same foundation (settings, plugins, MCP, permissions).
    Per-agent config (model, turns, budget, tools) comes from AgentConfig.
    """

    def __init__(
        self,
        config: TaskSummonerConfig,
        plugin_resolver: PluginResolver,
    ) -> None:
        self._config = config
        self._plugin_resolver = plugin_resolver
        self._env = self._build_env()

    def build(
        self,
        *,
        agent_config: AgentConfig,
        cwd: str,
        system_prompt: str = "",
    ) -> ClaudeAgentOptions:
        """Create ClaudeAgentOptions for a specific agent invocation."""
        return ClaudeAgentOptions(
            cwd=cwd,
            system_prompt=system_prompt,
            model=agent_config.model,
            max_turns=agent_config.max_turns,
            max_budget_usd=agent_config.max_budget_usd,
            allowed_tools=agent_config.tools,
            permission_mode="bypassPermissions",
            setting_sources=["user"],
            plugins=self._plugin_resolver.resolve(),
            env=self._env,
        )

    def _build_env(self) -> dict[str, str]:
        """Forward relevant env vars to the agent subprocess."""
        keys = [
            "ANTHROPIC_API_KEY",
            "ATLASSIAN_EMAIL",
            "ATLASSIAN_TOKEN",
            "SLACK_BOT_TOKEN",
            "SLACK_USER_ID",
        ]
        return {k: os.environ[k] for k in keys if os.environ.get(k)}
