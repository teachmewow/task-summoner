"""Tests for AgentProviderFactory."""

from __future__ import annotations

import pytest

from task_summoner.providers.agent import (
    AgentProviderFactory,
    ClaudeCodeAdapter,
    CodexAdapter,
)
from task_summoner.providers.config import (
    AgentProviderType,
    BoardProviderType,
    ClaudeCodeConfig,
    CodexConfig,
    JiraConfig,
    LinearConfig,
    ProviderConfig,
)


def _claude_config() -> ProviderConfig:
    return ProviderConfig(
        board=BoardProviderType.JIRA,
        board_config=JiraConfig(email="e", token="t"),
        agent=AgentProviderType.CLAUDE_CODE,
        agent_config=ClaudeCodeConfig(api_key="k"),
    )


def _codex_config() -> ProviderConfig:
    return ProviderConfig(
        board=BoardProviderType.JIRA,
        board_config=JiraConfig(email="e", token="t"),
        agent=AgentProviderType.CODEX,
        agent_config=CodexConfig(api_key="k"),
    )


def _linear_claude_config(team_id: str = "team-xyz") -> ProviderConfig:
    return ProviderConfig(
        board=BoardProviderType.LINEAR,
        board_config=LinearConfig(api_key="lk", team_id=team_id),
        agent=AgentProviderType.CLAUDE_CODE,
        agent_config=ClaudeCodeConfig(api_key="k"),
    )


class TestAgentProviderFactory:
    def test_create_claude_code_adapter(self):
        provider = AgentProviderFactory.create(_claude_config())
        assert isinstance(provider, ClaudeCodeAdapter)

    def test_create_codex_adapter(self):
        provider = AgentProviderFactory.create(_codex_config())
        assert isinstance(provider, CodexAdapter)

    def test_create_raises_when_config_type_mismatches_claude(self):
        config = _claude_config()
        config.agent_config = CodexConfig(api_key="k")
        with pytest.raises(ValueError, match="claude_code"):
            AgentProviderFactory.create(config)

    def test_create_raises_when_config_type_mismatches_codex(self):
        config = _codex_config()
        config.agent_config = ClaudeCodeConfig(api_key="k")
        with pytest.raises(ValueError, match="codex"):
            AgentProviderFactory.create(config)

    def test_claude_adapter_receives_linear_team_id(self):
        """ENG-111: team_id from LinearConfig must be threaded into the adapter."""
        provider = AgentProviderFactory.create(_linear_claude_config(team_id="team-fb14c704"))
        assert isinstance(provider, ClaudeCodeAdapter)
        assert provider._board_team_id == "team-fb14c704"

    def test_claude_adapter_has_no_team_id_with_jira_board(self):
        provider = AgentProviderFactory.create(_claude_config())
        assert isinstance(provider, ClaudeCodeAdapter)
        assert provider._board_team_id is None
