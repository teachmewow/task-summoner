"""Tests for Claude Code authentication (personal_session vs api_key)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from task_summoner.config import TaskSummonerConfig, _validate_claude_auth
from task_summoner.providers.agent.claude_code import (
    ClaudeCodeAdapter,
    claude_code_session_available,
)
from task_summoner.providers.config import (
    AgentProviderType,
    BoardProviderType,
    ClaudeCodeConfig,
    JiraConfig,
    ProviderConfig,
)


class TestSessionDetection:
    def test_returns_true_when_projects_dir_exists(self, tmp_path: Path):
        (tmp_path / "projects").mkdir()
        assert claude_code_session_available(tmp_path) is True

    def test_returns_true_when_history_jsonl_exists(self, tmp_path: Path):
        (tmp_path / "history.jsonl").touch()
        assert claude_code_session_available(tmp_path) is True

    def test_returns_false_when_home_missing(self, tmp_path: Path):
        assert claude_code_session_available(tmp_path / "nope") is False

    def test_returns_false_when_home_empty(self, tmp_path: Path):
        assert claude_code_session_available(tmp_path) is False


class TestClaudeCodeConfigDefaults:
    def test_auth_method_defaults_to_personal_session(self):
        config = ClaudeCodeConfig()
        assert config.auth_method == "personal_session"
        assert config.api_key is None

    def test_legacy_api_key_only_promotes_to_api_key_mode(self):
        """Constructing with just api_key (old API) should default to api_key mode."""
        config = ClaudeCodeConfig(api_key="sk-ant-abc")
        assert config.auth_method == "api_key"
        assert config.api_key == "sk-ant-abc"

    def test_explicit_personal_session_with_api_key_stays_personal(self):
        config = ClaudeCodeConfig(auth_method="personal_session", api_key="sk-unused")
        assert config.auth_method == "personal_session"


class TestAuthValidation:
    def test_personal_session_requires_session(self, tmp_path: Path):
        cc = ClaudeCodeConfig(auth_method="personal_session")
        with patch(
            "task_summoner.providers.agent.claude_code.claude_code_session_available",
            return_value=False,
        ):
            errors = _validate_claude_auth(cc)
        assert any("no Claude Code session detected" in e for e in errors)

    def test_personal_session_ok_when_session_detected(self):
        cc = ClaudeCodeConfig(auth_method="personal_session")
        with patch(
            "task_summoner.providers.agent.claude_code.claude_code_session_available",
            return_value=True,
        ):
            errors = _validate_claude_auth(cc)
        assert errors == []

    def test_api_key_requires_non_empty(self):
        cc = ClaudeCodeConfig(auth_method="api_key", api_key=None)
        errors = _validate_claude_auth(cc)
        assert any("api_key is empty" in e for e in errors)

    def test_api_key_ok_when_set(self):
        cc = ClaudeCodeConfig(auth_method="api_key", api_key="sk-ant-abc")
        errors = _validate_claude_auth(cc)
        assert errors == []


class TestAdapterEnvForwarding:
    def test_personal_session_does_not_forward_api_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
        adapter = ClaudeCodeAdapter(ClaudeCodeConfig(auth_method="personal_session"))
        env = adapter._build_env()
        assert "ANTHROPIC_API_KEY" not in env

    def test_api_key_mode_forwards_config_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        adapter = ClaudeCodeAdapter(
            ClaudeCodeConfig(auth_method="api_key", api_key="sk-from-config")
        )
        env = adapter._build_env()
        assert env["ANTHROPIC_API_KEY"] == "sk-from-config"

    def test_api_key_mode_config_value_wins_over_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
        adapter = ClaudeCodeAdapter(
            ClaudeCodeConfig(auth_method="api_key", api_key="sk-from-config")
        )
        env = adapter._build_env()
        assert env["ANTHROPIC_API_KEY"] == "sk-from-config"


class TestTaskSummonerConfigCheckConfig:
    def _build(self, cc: ClaudeCodeConfig, tmp_path: Path) -> TaskSummonerConfig:
        return TaskSummonerConfig(
            providers=ProviderConfig(
                board=BoardProviderType.JIRA,
                board_config=JiraConfig(email="e@x.com", token="t"),
                agent=AgentProviderType.CLAUDE_CODE,
                agent_config=cc,
            ),
            repos={"demo": str(tmp_path)},
            default_repo="demo",
        )

    def test_personal_session_with_session_passes(self, tmp_path: Path):
        config = self._build(ClaudeCodeConfig(auth_method="personal_session"), tmp_path)
        with patch(
            "task_summoner.providers.agent.claude_code.claude_code_session_available",
            return_value=True,
        ):
            errors = config.check_config()
        assert not any("claude_code" in e for e in errors)

    def test_personal_session_without_session_errors(self, tmp_path: Path):
        config = self._build(ClaudeCodeConfig(auth_method="personal_session"), tmp_path)
        with patch(
            "task_summoner.providers.agent.claude_code.claude_code_session_available",
            return_value=False,
        ):
            errors = config.check_config()
        assert any("no Claude Code session detected" in e for e in errors)

    def test_api_key_empty_errors(self, tmp_path: Path):
        config = self._build(ClaudeCodeConfig(auth_method="api_key", api_key=""), tmp_path)
        errors = config.check_config()
        assert any("api_key is empty" in e for e in errors)
