"""Shared fixtures for task-summoner tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from task_summoner.config import AgentConfig, RetryConfig, TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.providers.config import (
    AgentProviderType,
    BoardProviderType,
    ClaudeCodeConfig,
    JiraConfig,
    ProviderConfig,
)
from task_summoner.states.base import StateServices

_PLUGIN_PATH = str(
    Path(__file__).resolve().parents[1]
    / ".."
    / "aiops-claude-code"
    / "plugins"
    / "aiops-workflows"
)


def _test_provider_config() -> ProviderConfig:
    return ProviderConfig(
        board=BoardProviderType.JIRA,
        board_config=JiraConfig(
            email="test@example.com",
            token="test-token",
            watch_label="task-summoner",
        ),
        agent=AgentProviderType.CLAUDE_CODE,
        agent_config=ClaudeCodeConfig(
            api_key="test-key",
            plugin_mode="local",
            plugin_path=_PLUGIN_PATH,
        ),
    )


@pytest.fixture
def config(tmp_path: Path) -> TaskSummonerConfig:
    return TaskSummonerConfig(
        polling_interval_sec=5,
        artifacts_dir=str(tmp_path / "artifacts"),
        approval_timeout_hours=1,
        providers=_test_provider_config(),
        default_repo="test-repo",
        repos={"test-repo": str(tmp_path / "repo")},
        workspace_root=str(tmp_path / "workspaces"),
        doc_checker=AgentConfig(
            model="haiku", max_turns=5, max_budget_usd=1.0, tools=["Read"]
        ),
        standard=AgentConfig(model="sonnet", max_turns=10, max_budget_usd=5.0),
        heavy=AgentConfig(model="sonnet", max_turns=20, max_budget_usd=10.0),
        retry=RetryConfig(max_retries=2, base_delay_sec=1, max_backoff_sec=5),
    )


@pytest.fixture
def store(config: TaskSummonerConfig) -> StateStore:
    return StateStore(config.artifacts_dir)


@pytest.fixture
def sample_ticket() -> Ticket:
    return Ticket(
        key="LLMOPS-42",
        summary="Add retry logic to API client",
        description="Implement exponential backoff for HTTP requests",
        status="To Do",
        labels=["task-summoner"],
        assignee="matheus",
        acceptance_criteria="All HTTP calls should retry on 5xx errors",
    )


@pytest.fixture
def sample_context() -> TicketContext:
    return TicketContext(ticket_key="LLMOPS-42", state=TicketState.QUEUED)


@pytest.fixture
def mock_services() -> StateServices:
    """Mock StateServices with board + agent providers (M4 shape)."""
    return StateServices(
        board=AsyncMock(),
        workspace=AsyncMock(),
        agent=AsyncMock(),
        store=AsyncMock(),
    )
