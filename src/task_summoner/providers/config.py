"""Provider configuration models — used by factories to instantiate adapters."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class BoardProviderType(str, Enum):
    """Supported board providers."""

    JIRA = "jira"
    LINEAR = "linear"


class AgentProviderType(str, Enum):
    """Supported agent CLI providers."""

    CLAUDE_CODE = "claude_code"
    CODEX = "codex"


class JiraConfig(BaseModel):
    """Configuration for Jira board provider."""

    email: str
    token: str
    base_url: str | None = None
    watch_label: str = "task-summoner"


class LinearConfig(BaseModel):
    """Configuration for Linear board provider."""

    api_key: str
    team_id: str
    watch_label: str = "task-summoner"


class ClaudeCodeConfig(BaseModel):
    """Configuration for Claude Code agent provider."""

    api_key: str
    plugin_mode: str = "installed"
    plugin_path: str | None = None


class CodexConfig(BaseModel):
    """Configuration for Codex agent provider."""

    api_key: str


class ProviderConfig(BaseModel):
    """Top-level provider configuration."""

    board: BoardProviderType
    board_config: JiraConfig | LinearConfig
    agent: AgentProviderType
    agent_config: ClaudeCodeConfig | CodexConfig
