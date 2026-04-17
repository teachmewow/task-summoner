"""Tests for BoardProviderFactory."""

from __future__ import annotations

import pytest

from task_summoner.providers.board import BoardProviderFactory, JiraAdapter, LinearAdapter
from task_summoner.providers.config import (
    AgentProviderType,
    BoardProviderType,
    ClaudeCodeConfig,
    JiraConfig,
    LinearConfig,
    ProviderConfig,
)


def _jira_config() -> ProviderConfig:
    return ProviderConfig(
        board=BoardProviderType.JIRA,
        board_config=JiraConfig(email="e@x.com", token="t"),
        agent=AgentProviderType.CLAUDE_CODE,
        agent_config=ClaudeCodeConfig(api_key="k"),
    )


def _linear_config() -> ProviderConfig:
    return ProviderConfig(
        board=BoardProviderType.LINEAR,
        board_config=LinearConfig(api_key="k", team_id="team-123"),
        agent=AgentProviderType.CLAUDE_CODE,
        agent_config=ClaudeCodeConfig(api_key="k"),
    )


class TestBoardProviderFactory:
    def test_create_jira_adapter(self):
        provider = BoardProviderFactory.create(_jira_config())
        assert isinstance(provider, JiraAdapter)

    def test_create_linear_adapter(self):
        provider = BoardProviderFactory.create(_linear_config())
        assert isinstance(provider, LinearAdapter)

    def test_create_raises_when_config_type_mismatches_jira(self):
        config = _jira_config()
        config.board_config = LinearConfig(api_key="k", team_id="team")
        with pytest.raises(ValueError, match="jira"):
            BoardProviderFactory.create(config)

    def test_create_raises_when_config_type_mismatches_linear(self):
        config = _linear_config()
        config.board_config = JiraConfig(email="e@x.com", token="t")
        with pytest.raises(ValueError, match="linear"):
            BoardProviderFactory.create(config)
