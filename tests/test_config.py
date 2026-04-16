"""Tests for configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from task_summoner.config import TaskSummonerConfig


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    content = f"""
task_summoner:
  poll_interval_sec: 30
  artifacts_dir: "./artifacts"
  default_repo: "my-repo"
  repos:
    my-repo: "{tmp_path}"
  workspace:
    root: "{tmp_path}/workspaces"
  agents:
    doc_checker:
      model: "haiku"
      max_turns: 10
    standard:
      model: "opus"
    heavy:
      max_turns: 999
"""
    path = tmp_path / "config.yaml"
    path.write_text(content)
    return path


class TestConfigLoading:
    def test_load_from_yaml(self, config_file: Path):
        config = TaskSummonerConfig.load(config_file)
        assert config.poll_interval_sec == 30
        assert config.default_repo == "my-repo"

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

    def test_missing_file_returns_defaults(self, tmp_path: Path):
        config = TaskSummonerConfig.load(tmp_path / "nonexistent.yaml")
        assert config.poll_interval_sec == 15
        assert config.jira_label == "task-summoner"


class TestConfigValidation:
    def test_missing_api_key(self, config: TaskSummonerConfig):
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            errors = config.check_config()
            assert any("ANTHROPIC_API_KEY" in e for e in errors)
        finally:
            if old:
                os.environ["ANTHROPIC_API_KEY"] = old

    def test_missing_repo_path(self):
        config = TaskSummonerConfig(repos={"fake": "/nonexistent"}, default_repo="fake")
        errors = config.check_config()
        assert any("does not exist" in e for e in errors)

    def test_no_repos(self):
        config = TaskSummonerConfig(repos={})
        errors = config.check_config()
        assert any("No repos" in e for e in errors)


class TestResolveRepo:
    def test_resolve_from_label(self):
        config = TaskSummonerConfig(repos={"api": "/tmp/api", "ui": "/tmp/ui"}, default_repo="api")
        name, path = config.resolve_repo(["task-summoner", "repo:ui"])
        assert name == "ui"

    def test_resolve_fallback(self):
        config = TaskSummonerConfig(repos={"api": "/tmp/api"}, default_repo="api")
        name, _ = config.resolve_repo(["task-summoner"])
        assert name == "api"

    def test_unknown_label_raises(self):
        config = TaskSummonerConfig(repos={"api": "/tmp/api"}, default_repo="api")
        with pytest.raises(ValueError, match="Unknown repo"):
            config.resolve_repo(["repo:nope"])

    def test_no_default_raises(self):
        config = TaskSummonerConfig(repos={"api": "/tmp/api"}, default_repo="")
        with pytest.raises(ValueError):
            config.resolve_repo(["task-summoner"])
