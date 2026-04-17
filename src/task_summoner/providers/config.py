"""Provider configuration models — used by factories to instantiate adapters."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, model_validator


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
    """Configuration for Claude Code agent provider.

    Two authentication modes:
    - `personal_session` (default): inherit the user's logged-in Claude Code session.
      No API key needed — the spawned agent uses the existing `claude login` billing.
    - `api_key`: pass an explicit Anthropic API key to the agent.
    """

    auth_method: Literal["personal_session", "api_key"] = "personal_session"
    api_key: str | None = None
    plugin_mode: str = "installed"
    plugin_path: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _backward_compat_api_key(cls, values: object) -> object:
        """Legacy configs may set api_key without auth_method — keep them working.

        If `api_key` is set and `auth_method` is not explicitly provided, assume the
        user intended `api_key` mode. New configs from the wizard always set
        `auth_method` explicitly so this only fires for hand-written legacy YAML
        (and every test constructed before this field existed).
        """
        if isinstance(values, dict):
            has_api_key = bool(values.get("api_key"))
            has_auth_method = "auth_method" in values
            if has_api_key and not has_auth_method:
                values["auth_method"] = "api_key"
        return values


class CodexConfig(BaseModel):
    """Configuration for Codex agent provider."""

    api_key: str


class ProviderConfig(BaseModel):
    """Top-level provider configuration."""

    board: BoardProviderType
    board_config: JiraConfig | LinearConfig
    agent: AgentProviderType
    agent_config: ClaudeCodeConfig | CodexConfig
