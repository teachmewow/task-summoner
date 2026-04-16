"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from task_summoner.config import TaskSummonerConfig
from task_summoner.providers.config import (
    AgentProviderType,
    BoardProviderType,
    ClaudeCodeConfig,
    JiraConfig,
    LinearConfig,
    ProviderConfig,
)


def _base_provider_config() -> ProviderConfig:
    return ProviderConfig(
        board=BoardProviderType.JIRA,
        board_config=JiraConfig(email="e@x.com", token="t"),
        agent=AgentProviderType.CLAUDE_CODE,
        agent_config=ClaudeCodeConfig(api_key="k"),
    )


@pytest.fixture
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ATLASSIAN_EMAIL", "me@example.com")
    monkeypatch.setenv("ATLASSIAN_TOKEN", "atl-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anth-key")

    content = f"""
providers:
  board:
    type: jira
    jira:
      email: ${{ATLASSIAN_EMAIL}}
      token: ${{ATLASSIAN_TOKEN}}
      watch_label: task-summoner
  agent:
    type: claude_code
    claude_code:
      api_key: ${{ANTHROPIC_API_KEY}}
      plugin_mode: installed

repos:
  my-repo: "{tmp_path}"

default_repo: my-repo

polling_interval_sec: 30
workspace_root: "{tmp_path}/workspaces"

agent_profiles:
  doc_checker:
    model: haiku
    max_turns: 10
  standard:
    model: opus
  heavy:
    max_turns: 999
"""
    path = tmp_path / "config.yaml"
    path.write_text(content)
    return path


class TestConfigLoading:
    def test_load_from_yaml(self, config_file: Path):
        config = TaskSummonerConfig.load(config_file)
        assert config.polling_interval_sec == 30
        assert config.poll_interval_sec == 30  # legacy property
        assert config.default_repo == "my-repo"

    def test_env_var_substitution(self, config_file: Path):
        config = TaskSummonerConfig.load(config_file)
        assert isinstance(config.providers.board_config, JiraConfig)
        assert config.providers.board_config.email == "me@example.com"
        assert config.providers.board_config.token == "atl-token"
        assert isinstance(config.providers.agent_config, ClaudeCodeConfig)
        assert config.providers.agent_config.api_key == "anth-key"

    def test_doc_checker_override(self, config_file: Path):
        config = TaskSummonerConfig.load(config_file)
        assert config.doc_checker.model == "haiku"
        assert config.doc_checker.max_turns == 10

    def test_standard_override(self, config_file: Path):
        config = TaskSummonerConfig.load(config_file)
        assert config.standard.model == "opus"

    def test_heavy_override(self, config_file: Path):
        config = TaskSummonerConfig.load(config_file)
        assert config.heavy.max_turns == 999

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="setup"):
            TaskSummonerConfig.load(tmp_path / "nonexistent.yaml")

    def test_missing_providers_block_raises(self, tmp_path: Path):
        path = tmp_path / "config.yaml"
        path.write_text("repos:\n  x: /tmp\n")
        with pytest.raises(ValueError, match="providers"):
            TaskSummonerConfig.load(path)


class TestConfigValidation:
    def test_missing_jira_token(self):
        config = TaskSummonerConfig(
            providers=ProviderConfig(
                board=BoardProviderType.JIRA,
                board_config=JiraConfig(email="e@x.com", token=""),
                agent=AgentProviderType.CLAUDE_CODE,
                agent_config=ClaudeCodeConfig(api_key="k"),
            ),
            repos={},
        )
        errors = config.check_config()
        assert any("token" in e for e in errors)

    def test_missing_linear_credentials(self):
        config = TaskSummonerConfig(
            providers=ProviderConfig(
                board=BoardProviderType.LINEAR,
                board_config=LinearConfig(api_key="", team_id=""),
                agent=AgentProviderType.CLAUDE_CODE,
                agent_config=ClaudeCodeConfig(api_key="k"),
            ),
            repos={},
        )
        errors = config.check_config()
        assert any("api_key" in e for e in errors)
        assert any("team_id" in e for e in errors)

    def test_missing_repo_path(self):
        config = TaskSummonerConfig(
            providers=_base_provider_config(),
            repos={"fake": "/nonexistent"},
            default_repo="fake",
        )
        errors = config.check_config()
        assert any("does not exist" in e for e in errors)

    def test_no_repos(self):
        config = TaskSummonerConfig(providers=_base_provider_config(), repos={})
        errors = config.check_config()
        assert any("No repos" in e for e in errors)


class TestResolveRepo:
    def test_resolve_from_label(self):
        config = TaskSummonerConfig(
            providers=_base_provider_config(),
            repos={"api": "/tmp/api", "ui": "/tmp/ui"},
            default_repo="api",
        )
        name, _ = config.resolve_repo(["task-summoner", "repo:ui"])
        assert name == "ui"

    def test_resolve_fallback(self):
        config = TaskSummonerConfig(
            providers=_base_provider_config(),
            repos={"api": "/tmp/api"},
            default_repo="api",
        )
        name, _ = config.resolve_repo(["task-summoner"])
        assert name == "api"

    def test_unknown_label_raises(self):
        config = TaskSummonerConfig(
            providers=_base_provider_config(),
            repos={"api": "/tmp/api"},
            default_repo="api",
        )
        with pytest.raises(ValueError, match="Unknown repo"):
            config.resolve_repo(["repo:nope"])

    def test_no_default_raises(self):
        config = TaskSummonerConfig(
            providers=_base_provider_config(),
            repos={"api": "/tmp/api"},
            default_repo="",
        )
        with pytest.raises(ValueError):
            config.resolve_repo(["task-summoner"])


class TestProviderDispatch:
    def test_build_provider_config_returns_jira(self):
        config = TaskSummonerConfig(
            providers=_base_provider_config(),
            repos={"api": "/tmp/api"},
            default_repo="api",
        )
        provider_config = config.build_provider_config()
        assert provider_config.board == BoardProviderType.JIRA

    def test_build_provider_config_returns_linear(self):
        config = TaskSummonerConfig(
            providers=ProviderConfig(
                board=BoardProviderType.LINEAR,
                board_config=LinearConfig(api_key="k", team_id="team"),
                agent=AgentProviderType.CLAUDE_CODE,
                agent_config=ClaudeCodeConfig(api_key="ak"),
            ),
            repos={"api": "/tmp/api"},
            default_repo="api",
        )
        provider_config = config.build_provider_config()
        assert provider_config.board == BoardProviderType.LINEAR
