"""Configuration loading — YAML file + .env + env var overrides."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class AgentConfig(BaseModel):
    """Config for a single agent profile."""

    enabled: bool = True
    model: str = "opus"
    max_turns: int = Field(default=200, ge=1)
    max_budget_usd: float = Field(default=50.0, gt=0)
    tools: list[str] = Field(
        default_factory=lambda: ["Read", "Glob", "Grep", "Bash", "Edit", "Write", "Skill"]
    )


class RetryConfig(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    base_delay_sec: int = Field(default=10, ge=1)
    max_backoff_sec: int = Field(default=300, ge=1)


class TaskSummonerConfig(BaseModel):
    """Root configuration — loaded from config.yaml + .env."""

    model_config = {"arbitrary_types_allowed": True}

    # Polling
    poll_interval_sec: int = Field(default=15, ge=1)
    artifacts_dir: str = "./artifacts"
    approval_timeout_hours: int = Field(default=24, ge=0)

    # Timeouts
    acli_timeout_sec: int = Field(default=30, ge=5)
    git_timeout_sec: int = Field(default=60, ge=10)

    # Jira
    jira_label: str = "task-summoner"
    jira_excluded_statuses: list[str] = Field(
        default_factory=lambda: ["Done", "Closed"]
    )

    # Repos
    default_repo: str = ""
    repos: dict[str, str] = Field(default_factory=dict)

    # Plugin
    plugin_mode: str = Field(
        default="installed",
        description="How the aiops-workflows plugin is loaded: 'installed' (from user's Claude Code) or 'local' (from plugin_path)",
    )
    plugin_path: str = Field(
        default="",
        description="Path to aiops-workflows plugin directory (only used when plugin_mode='local')",
    )

    # Workspace
    workspace_root: str = "/tmp/task-summoner-workspaces"

    # Agent profiles — states reference these by name
    doc_checker: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="haiku", max_turns=20, max_budget_usd=5.0,
            tools=["Read", "Glob", "Grep", "Bash"],
        ),
        description="Light agent for doc triage",
    )
    standard: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="sonnet", max_turns=200, max_budget_usd=50.0,
        ),
        description="Standard agent for planning, doc creation, reviews",
    )
    heavy: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="sonnet", max_turns=500, max_budget_usd=50.0,
        ),
        description="Heavy agent for implementation",
    )

    # Retry
    retry: RetryConfig = Field(default_factory=RetryConfig)

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> TaskSummonerConfig:
        """Load from YAML file. Expands ~ in paths. Falls back to defaults."""
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        bd = raw.get("task_summoner", raw)

        config = cls(
            poll_interval_sec=bd.get("poll_interval_sec", 15),
            artifacts_dir=_expand(bd.get("artifacts_dir", "./artifacts")),
            approval_timeout_hours=bd.get("approval_timeout_hours", 24),
            jira_label=bd.get("jira", {}).get("label", "task-summoner"),
            jira_excluded_statuses=bd.get("jira", {}).get(
                "excluded_statuses", ["Done", "Closed"]
            ),
            default_repo=bd.get("default_repo", ""),
            repos={k: _expand(v) for k, v in (bd.get("repos") or {}).items()},
            plugin_mode=bd.get("plugin_mode", "installed"),
            plugin_path=_expand(bd.get("plugin_path", "")),
            workspace_root=_expand(
                bd.get("workspace", {}).get("root", "/tmp/task-summoner-workspaces")
            ),
            retry=_parse_retry(bd.get("retry", {})),
        )

        agents_raw = bd.get("agents", {})
        if "doc_checker" in agents_raw:
            config.doc_checker = _parse_agent_config(agents_raw["doc_checker"], config.doc_checker)
        if "standard" in agents_raw:
            config.standard = _parse_agent_config(agents_raw["standard"], config.standard)
        if "heavy" in agents_raw:
            config.heavy = _parse_agent_config(agents_raw["heavy"], config.heavy)

        return config

    def resolve_repo(self, labels: list[str]) -> tuple[str, str]:
        """Resolve repo name and path from ticket labels (repo:<name>)."""
        for label in labels:
            if label.startswith("repo:"):
                repo_name = label[len("repo:"):]
                if repo_name in self.repos:
                    return repo_name, self.repos[repo_name]
                raise ValueError(f"Unknown repo '{repo_name}'. Available: {list(self.repos.keys())}")
        if self.default_repo and self.default_repo in self.repos:
            return self.default_repo, self.repos[self.default_repo]
        raise ValueError(f"No 'repo:<name>' label and no valid default_repo. Available: {list(self.repos.keys())}")

    def build_plugin_resolver(self):
        """Create a PluginResolver from this config's plugin settings."""
        from task_summoner.agents.plugin_resolver import PluginMode, PluginResolver
        try:
            mode = PluginMode(self.plugin_mode)
        except ValueError:
            mode = PluginMode.INSTALLED
        return PluginResolver(mode=mode, plugin_path=self.plugin_path)

    def check_config(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors = []
        if not os.environ.get("ANTHROPIC_API_KEY"):
            errors.append("ANTHROPIC_API_KEY env var not set")
        if self.plugin_mode not in ("installed", "local"):
            errors.append(f"plugin_mode must be 'installed' or 'local', got '{self.plugin_mode}'")
        errors.extend(self.build_plugin_resolver().validate())
        if not self.repos:
            errors.append("No repos configured")
        if self.default_repo and self.default_repo not in self.repos:
            errors.append(f"default_repo '{self.default_repo}' not in repos")
        for repo_name, repo_path in self.repos.items():
            if not Path(repo_path).is_dir():
                errors.append(f"Repo path for {repo_name} does not exist: {repo_path}")
        return errors


def _expand(path: str) -> str:
    return str(Path(path).expanduser())


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
