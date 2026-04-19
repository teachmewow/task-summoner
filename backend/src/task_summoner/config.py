"""Configuration loading — provider-agnostic YAML schema with env var substitution.

New config.yaml format (required):

```yaml
providers:
  board:
    type: linear          # or: jira
    linear:
      api_key: ${LINEAR_API_KEY}
      team_id: "fb14..."
      watch_label: task-summoner
    # jira:
    #   email: ${ATLASSIAN_EMAIL}
    #   token: ${ATLASSIAN_TOKEN}
    #   watch_label: task-summoner
  agent:
    type: claude_code     # or: codex
    claude_code:
      api_key: ${ANTHROPIC_API_KEY}
      plugin_mode: installed
      # plugin_path: ~/path/to/task-summoner-workflows

repos:
  my-project: ~/code/my-project

default_repo: my-project

agent_profiles:
  doc_checker: { model: haiku, max_turns: 20, max_budget_usd: 5 }
  standard:    { model: sonnet, max_turns: 200, max_budget_usd: 50 }
  heavy:       { model: opus,   max_turns: 500, max_budget_usd: 50 }

polling_interval_sec: 15
workspace_root: /tmp/task-summoner-workspaces
artifacts_dir: ./artifacts
approval_timeout_hours: 24

retry:
  max_retries: 3
  base_delay_sec: 10
  max_backoff_sec: 300
```
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from task_summoner.providers.agent import claude_code as claude_code_module
from task_summoner.providers.agent.claude_code.plugin_resolver import (
    PluginMode,
    PluginResolver,
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
from task_summoner.utils import expand as _expand_path

# Project `.env` is canonical and wins over shell exports.
# Without `override=True`, a stale `LINEAR_API_KEY` (or similar) exported in the
# user's shell silently shadows the per-project value, causing cross-workspace
# API calls that are very hard to diagnose.
load_dotenv(override=True)

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


class AgentConfig(BaseModel):
    """Config for a single agent profile."""

    enabled: bool = True
    model: str = "opus"
    max_turns: int = Field(default=200, ge=1)
    max_budget_usd: float = Field(default=50.0, gt=0)
    tools: list[str] = Field(
        default_factory=lambda: [
            "Read",
            "Glob",
            "Grep",
            "Bash",
            "Edit",
            "Write",
            "Skill",
        ]
    )


class RetryConfig(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    base_delay_sec: int = Field(default=10, ge=1)
    max_backoff_sec: int = Field(default=300, ge=1)


class TaskSummonerConfig(BaseModel):
    """Root configuration — loaded from config.yaml + .env."""

    model_config = {"arbitrary_types_allowed": True}

    polling_interval_sec: int = Field(default=15, ge=1)
    artifacts_dir: str = "./artifacts"
    approval_timeout_hours: int = Field(default=24, ge=0)
    acli_timeout_sec: int = Field(default=30, ge=5)
    git_timeout_sec: int = Field(default=60, ge=10)

    providers: ProviderConfig

    default_repo: str = ""
    repos: dict[str, str] = Field(default_factory=dict)

    workspace_root: str = "/tmp/task-summoner-workspaces"

    doc_checker: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="haiku",
            max_turns=20,
            max_budget_usd=5.0,
            tools=["Read", "Glob", "Grep", "Bash"],
        ),
    )
    standard: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="sonnet",
            max_turns=200,
            max_budget_usd=50.0,
        ),
    )
    heavy: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="sonnet",
            max_turns=500,
            max_budget_usd=50.0,
        ),
    )

    retry: RetryConfig = Field(default_factory=RetryConfig)

    monthly_budget_usd: float | None = Field(default=None, ge=0.0)

    @property
    def poll_interval_sec(self) -> int:
        return self.polling_interval_sec

    @property
    def plugin_mode(self) -> str:
        if isinstance(self.providers.agent_config, ClaudeCodeConfig):
            return self.providers.agent_config.plugin_mode
        return "installed"

    @property
    def plugin_path(self) -> str:
        if isinstance(self.providers.agent_config, ClaudeCodeConfig):
            return self.providers.agent_config.plugin_path or ""
        return ""

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> TaskSummonerConfig:
        """Load from YAML file. Expands `~`, resolves `${ENV_VAR}` placeholders."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"Config file not found: {path}. Run `task-summoner setup` to create one."
            )

        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        raw = _substitute_env(raw)

        providers_raw = raw.get("providers")
        if not providers_raw:
            raise ValueError(
                "Config must contain a `providers:` block. "
                "See config.yaml.example for the required schema."
            )

        providers = _parse_providers(providers_raw)

        config = cls(
            polling_interval_sec=int(raw.get("polling_interval_sec", 15)),
            artifacts_dir=_expand(raw.get("artifacts_dir", "./artifacts")),
            approval_timeout_hours=int(raw.get("approval_timeout_hours", 24)),
            providers=providers,
            default_repo=raw.get("default_repo", ""),
            repos={k: _expand(v) for k, v in (raw.get("repos") or {}).items()},
            workspace_root=_expand(raw.get("workspace_root", "/tmp/task-summoner-workspaces")),
            retry=_parse_retry(raw.get("retry", {})),
            monthly_budget_usd=raw.get("monthly_budget_usd"),
        )

        profiles_raw = raw.get("agent_profiles", {})
        if "doc_checker" in profiles_raw:
            config.doc_checker = _parse_agent_config(
                profiles_raw["doc_checker"], config.doc_checker
            )
        if "standard" in profiles_raw:
            config.standard = _parse_agent_config(profiles_raw["standard"], config.standard)
        if "heavy" in profiles_raw:
            config.heavy = _parse_agent_config(profiles_raw["heavy"], config.heavy)

        return config

    def resolve_repo(self, labels: list[str]) -> tuple[str, str]:
        """Resolve repo name and path from ticket labels (repo:<name>)."""
        for label in labels:
            if label.startswith("repo:"):
                repo_name = label[len("repo:") :]
                if repo_name in self.repos:
                    return repo_name, self.repos[repo_name]
                raise ValueError(
                    f"Unknown repo '{repo_name}'. Available: {list(self.repos.keys())}"
                )
        if self.default_repo and self.default_repo in self.repos:
            return self.default_repo, self.repos[self.default_repo]
        raise ValueError(
            "No 'repo:<name>' label and no valid default_repo. "
            f"Available: {list(self.repos.keys())}"
        )

    def build_plugin_resolver(self):
        """Create a PluginResolver from the Claude Code config (if active)."""
        try:
            mode = PluginMode(self.plugin_mode)
        except ValueError:
            mode = PluginMode.INSTALLED
        return PluginResolver(mode=mode, plugin_path=self.plugin_path)

    def build_provider_config(self) -> ProviderConfig:
        """Return the parsed provider config. Kept for orchestrator API stability."""
        return self.providers

    def check_config(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []

        if self.providers.board == BoardProviderType.JIRA:
            jira = self.providers.board_config
            if isinstance(jira, JiraConfig):
                if not jira.email:
                    errors.append("providers.board.jira.email is empty")
                if not jira.token:
                    errors.append("providers.board.jira.token is empty")
        elif self.providers.board == BoardProviderType.LINEAR:
            linear = self.providers.board_config
            if isinstance(linear, LinearConfig):
                if not linear.api_key:
                    errors.append("providers.board.linear.api_key is empty")
                if not linear.team_id:
                    errors.append("providers.board.linear.team_id is empty")

        if self.providers.agent == AgentProviderType.CLAUDE_CODE:
            cc = self.providers.agent_config
            if isinstance(cc, ClaudeCodeConfig):
                errors.extend(_validate_claude_auth(cc))
                if cc.plugin_mode not in ("installed", "local"):
                    errors.append(
                        f"plugin_mode must be 'installed' or 'local', got '{cc.plugin_mode}'"
                    )
                errors.extend(self.build_plugin_resolver().validate())

        if not self.repos:
            errors.append("No repos configured")
        if self.default_repo and self.default_repo not in self.repos:
            errors.append(f"default_repo '{self.default_repo}' not in repos")
        for repo_name, repo_path in self.repos.items():
            if not Path(repo_path).is_dir():
                errors.append(f"Repo path for {repo_name} does not exist: {repo_path}")
        return errors


def _validate_claude_auth(cc: ClaudeCodeConfig) -> list[str]:
    """Return validation errors for the Claude Code auth configuration."""
    if cc.auth_method == "personal_session":
        if not claude_code_module.claude_code_session_available():
            return [
                "providers.agent.claude_code.auth_method='personal_session' "
                "but no Claude Code session detected. Run `claude login` first "
                "or switch to auth_method='api_key'."
            ]
        return []
    if cc.auth_method == "api_key":
        if not cc.api_key:
            return ["providers.agent.claude_code.auth_method='api_key' but api_key is empty."]
        return []
    return [f"Unknown auth_method: {cc.auth_method!r}"]


def _expand(path: str) -> str:
    return _expand_path(path)


def _substitute_env(data: Any) -> Any:
    """Recursively replace `${VAR}` placeholders with os.environ values."""
    if isinstance(data, str):

        def replace(match: re.Match[str]) -> str:
            var = match.group(1)
            return os.environ.get(var, "")

        return _ENV_VAR_PATTERN.sub(replace, data)
    if isinstance(data, dict):
        return {k: _substitute_env(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_substitute_env(v) for v in data]
    return data


def _parse_providers(raw: dict[str, Any]) -> ProviderConfig:
    board_raw = raw.get("board") or {}
    agent_raw = raw.get("agent") or {}

    try:
        board_type = BoardProviderType(board_raw.get("type", ""))
    except ValueError as e:
        raise ValueError(
            f"Invalid providers.board.type: "
            f"{board_raw.get('type')!r}. Expected one of: "
            f"{[t.value for t in BoardProviderType]}"
        ) from e

    try:
        agent_type = AgentProviderType(agent_raw.get("type", ""))
    except ValueError as e:
        raise ValueError(
            f"Invalid providers.agent.type: "
            f"{agent_raw.get('type')!r}. Expected one of: "
            f"{[t.value for t in AgentProviderType]}"
        ) from e

    board_config = _parse_board_config(board_type, board_raw)
    agent_config = _parse_agent_config_typed(agent_type, agent_raw)

    return ProviderConfig(
        board=board_type,
        board_config=board_config,
        agent=agent_type,
        agent_config=agent_config,
    )


def _parse_board_config(
    board_type: BoardProviderType, raw: dict[str, Any]
) -> JiraConfig | LinearConfig:
    if board_type == BoardProviderType.JIRA:
        data = raw.get("jira") or {}
        return JiraConfig(**data)
    data = raw.get("linear") or {}
    return LinearConfig(**data)


def _parse_agent_config_typed(
    agent_type: AgentProviderType, raw: dict[str, Any]
) -> ClaudeCodeConfig | CodexConfig:
    if agent_type == AgentProviderType.CLAUDE_CODE:
        data = raw.get("claude_code") or {}
        if "plugin_path" in data and data["plugin_path"]:
            data["plugin_path"] = _expand(data["plugin_path"])
        return ClaudeCodeConfig(**data)
    data = raw.get("codex") or {}
    return CodexConfig(**data)


def _parse_agent_config(raw: dict, defaults: AgentConfig) -> AgentConfig:
    return AgentConfig(
        enabled=raw.get("enabled", defaults.enabled),
        model=raw.get("model", defaults.model),
        max_turns=raw.get("max_turns", defaults.max_turns),
        max_budget_usd=raw.get("max_budget_usd", defaults.max_budget_usd),
        tools=raw.get("tools", defaults.tools),
    )


def _parse_retry(raw: dict) -> RetryConfig:
    return RetryConfig(
        max_retries=raw.get("max_retries", 3),
        base_delay_sec=raw.get("base_delay_sec", 10),
        max_backoff_sec=raw.get("max_backoff_sec", 300),
    )
