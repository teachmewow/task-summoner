"""Tests for the setup wizard — focus on config rendering, not interactive prompts."""

from __future__ import annotations

import yaml

from task_summoner.providers.config import (
    AgentProviderType,
    BoardProviderType,
    ClaudeCodeConfig,
    CodexConfig,
    JiraConfig,
    LinearConfig,
)
from task_summoner.setup_wizard import _render_config_yaml


class TestRenderConfigYaml:
    def test_jira_plus_claude_code(self):
        rendered = _render_config_yaml(
            board_type=BoardProviderType.JIRA,
            board_config=JiraConfig(
                email="${ATLASSIAN_EMAIL}",
                token="${ATLASSIAN_TOKEN}",
                watch_label="task-summoner",
            ),
            agent_type=AgentProviderType.CLAUDE_CODE,
            agent_config=ClaudeCodeConfig(
                api_key="${ANTHROPIC_API_KEY}",
                plugin_mode="installed",
            ),
            repos={"my-repo": "/tmp/my-repo"},
            default_repo="my-repo",
            polling_interval_sec=10,
            workspace_root="/tmp/ws",
        )
        data = yaml.safe_load(rendered)
        assert data["providers"]["board"]["type"] == "jira"
        assert data["providers"]["board"]["jira"]["email"] == "${ATLASSIAN_EMAIL}"
        assert data["providers"]["agent"]["type"] == "claude_code"
        assert data["providers"]["agent"]["claude_code"]["plugin_mode"] == "installed"
        assert data["repos"] == {"my-repo": "/tmp/my-repo"}
        assert data["default_repo"] == "my-repo"
        assert data["polling_interval_sec"] == 10

    def test_linear_plus_codex(self):
        rendered = _render_config_yaml(
            board_type=BoardProviderType.LINEAR,
            board_config=LinearConfig(
                api_key="${LINEAR_API_KEY}",
                team_id="team-uuid",
                watch_label="task-summoner",
            ),
            agent_type=AgentProviderType.CODEX,
            agent_config=CodexConfig(api_key="${OPENAI_API_KEY}"),
            repos={"api": "/code/api", "ui": "/code/ui"},
            default_repo="api",
            polling_interval_sec=15,
            workspace_root="/tmp/ws",
        )
        data = yaml.safe_load(rendered)
        assert data["providers"]["board"]["type"] == "linear"
        assert data["providers"]["board"]["linear"]["team_id"] == "team-uuid"
        assert data["providers"]["agent"]["type"] == "codex"
        assert data["providers"]["agent"]["codex"]["api_key"] == "${OPENAI_API_KEY}"
        assert set(data["repos"]) == {"api", "ui"}

    def test_omits_default_repo_when_empty(self):
        rendered = _render_config_yaml(
            board_type=BoardProviderType.LINEAR,
            board_config=LinearConfig(api_key="k", team_id="t"),
            agent_type=AgentProviderType.CLAUDE_CODE,
            agent_config=ClaudeCodeConfig(api_key="k"),
            repos={},
            default_repo="",
            polling_interval_sec=10,
            workspace_root="/tmp/ws",
        )
        data = yaml.safe_load(rendered)
        assert "default_repo" not in data

    def test_round_trip_produces_loadable_config(self, tmp_path, monkeypatch):
        """Wizard output must be readable by TaskSummonerConfig.load()."""
        from task_summoner.config import TaskSummonerConfig

        monkeypatch.setenv("LINEAR_API_KEY", "lin-key")
        repo_path = tmp_path / "demo"
        repo_path.mkdir()

        rendered = _render_config_yaml(
            board_type=BoardProviderType.LINEAR,
            board_config=LinearConfig(
                api_key="${LINEAR_API_KEY}",
                team_id="team-uuid",
            ),
            agent_type=AgentProviderType.CLAUDE_CODE,
            agent_config=ClaudeCodeConfig(api_key="ak"),
            repos={"demo": str(repo_path)},
            default_repo="demo",
            polling_interval_sec=12,
            workspace_root=str(tmp_path / "ws"),
        )

        path = tmp_path / "config.yaml"
        path.write_text(rendered)

        config = TaskSummonerConfig.load(path)
        assert isinstance(config.providers.board_config, LinearConfig)
        assert config.providers.board_config.api_key == "lin-key"
        assert config.polling_interval_sec == 12
        assert config.default_repo == "demo"
