"""AgentProviderFactory — instantiates the correct AgentProvider from config."""

from __future__ import annotations

from task_summoner.providers.agent.claude_code import ClaudeCodeAdapter
from task_summoner.providers.agent.codex import CodexAdapter
from task_summoner.providers.agent.protocol import AgentProvider
from task_summoner.providers.config import (
    AgentProviderType,
    ClaudeCodeConfig,
    CodexConfig,
    ProviderConfig,
)


class AgentProviderFactory:
    """Creates an AgentProvider instance based on the provider type in config."""

    @staticmethod
    def create(config: ProviderConfig) -> AgentProvider:
        match config.agent:
            case AgentProviderType.CLAUDE_CODE:
                if not isinstance(config.agent_config, ClaudeCodeConfig):
                    raise ValueError(
                        "Agent provider is 'claude_code' but agent_config is not ClaudeCodeConfig"
                    )
                return ClaudeCodeAdapter(config.agent_config)
            case AgentProviderType.CODEX:
                if not isinstance(config.agent_config, CodexConfig):
                    raise ValueError(
                        "Agent provider is 'codex' but agent_config is not CodexConfig"
                    )
                return CodexAdapter(config.agent_config)
            case _:
                raise ValueError(f"Unknown agent provider: {config.agent}")
