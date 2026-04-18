"""Unit tests for the user_config module (resolution + validation + persistence)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from task_summoner import user_config
from task_summoner.user_config import (
    UserConfigError,
    get_docs_repo,
    resolve_all,
    resolve_user_config_value,
    set_value,
    unset_value,
    user_config_dir,
    user_config_path,
)


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect XDG_CONFIG_HOME to tmp so tests never touch the real user config."""
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    # Ensure docs_repo env var is not polluted from the developer's shell.
    monkeypatch.delenv("TASK_SUMMONER_DOCS_REPO", raising=False)
    return xdg


def _make_docs_repo(root: Path) -> Path:
    """Create a directory that satisfies all docs_repo validation rules."""
    repo = root / "docs-repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    marker_dir = repo / ".task-summoner"
    marker_dir.mkdir()
    (marker_dir / "config.yml").write_text("version: 1\n")
    return repo


class TestUserConfigDir:
    def test_honors_xdg_config_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "custom"))
        assert user_config_dir() == tmp_path / "custom" / "task-summoner"

    def test_defaults_to_home_dotconfig_when_xdg_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        assert user_config_dir() == tmp_path / ".config" / "task-summoner"

    def test_defaults_when_xdg_empty_string(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", "")
        monkeypatch.setenv("HOME", str(tmp_path))
        assert user_config_dir() == tmp_path / ".config" / "task-summoner"

    def test_expands_tilde_in_xdg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", "~/cfg")
        assert user_config_dir() == tmp_path / "cfg" / "task-summoner"

    def test_config_path_is_json(self):
        assert user_config_path().name == "config.json"


class TestResolveUserConfigValue:
    def test_env_var_takes_precedence_over_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Write a file value, then set env — env wins.
        repo = _make_docs_repo(tmp_path)
        set_value("docs_repo", str(repo))
        monkeypatch.setenv("TASK_SUMMONER_DOCS_REPO", "/from/env")

        resolved = resolve_user_config_value("docs_repo")

        assert resolved.value == "/from/env"
        assert resolved.source == "env"

    def test_file_used_when_env_unset(self, tmp_path: Path):
        repo = _make_docs_repo(tmp_path)
        set_value("docs_repo", str(repo))

        resolved = resolve_user_config_value("docs_repo")

        assert resolved.value == str(repo)
        assert resolved.source == "file"

    def test_unset_when_nothing_configured(self):
        resolved = resolve_user_config_value("docs_repo")

        assert resolved.value is None
        assert resolved.source == "unset"

    def test_empty_env_var_falls_through_to_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        repo = _make_docs_repo(tmp_path)
        set_value("docs_repo", str(repo))
        monkeypatch.setenv("TASK_SUMMONER_DOCS_REPO", "")

        resolved = resolve_user_config_value("docs_repo")

        assert resolved.source == "file"
        assert resolved.value == str(repo)

    def test_unknown_key_raises(self):
        with pytest.raises(UserConfigError, match="Unknown config key"):
            resolve_user_config_value("bogus")

    def test_corrupt_file_is_treated_as_empty(self, isolated_config_dir: Path):
        path = user_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")

        resolved = resolve_user_config_value("docs_repo")

        assert resolved.source == "unset"

    def test_non_string_file_values_ignored(self, isolated_config_dir: Path):
        path = user_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"docs_repo": 42}))

        resolved = resolve_user_config_value("docs_repo")

        assert resolved.source == "unset"


class TestResolveAll:
    def test_returns_an_entry_per_key(self):
        results = resolve_all()
        assert {r.key for r in results} == set(user_config.USER_CONFIG_KEYS)


class TestGetDocsRepoHelper:
    def test_returns_none_when_unset(self):
        assert get_docs_repo() is None

    def test_returns_env_when_set(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TASK_SUMMONER_DOCS_REPO", "/x/y")
        assert get_docs_repo() == "/x/y"


class TestSetValueValidation:
    def test_accepts_valid_docs_repo(self, tmp_path: Path):
        repo = _make_docs_repo(tmp_path)

        set_value("docs_repo", str(repo))

        assert json.loads(user_config_path().read_text()) == {"docs_repo": str(repo)}

    def test_rejects_relative_path(self):
        with pytest.raises(UserConfigError, match="absolute path"):
            set_value("docs_repo", "relative/path")

    def test_rejects_empty_value(self):
        with pytest.raises(UserConfigError, match="cannot be empty"):
            set_value("docs_repo", "")

    def test_rejects_nonexistent_path(self, tmp_path: Path):
        missing = tmp_path / "does-not-exist"
        with pytest.raises(UserConfigError, match="does not exist"):
            set_value("docs_repo", str(missing))

    def test_rejects_file_instead_of_dir(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(UserConfigError, match="not a directory"):
            set_value("docs_repo", str(f))

    def test_rejects_non_git_dir(self, tmp_path: Path):
        non_git = tmp_path / "plain-dir"
        non_git.mkdir()
        # Marker alone doesn't help — git repo check must fail first.
        (non_git / ".task-summoner").mkdir()
        (non_git / ".task-summoner" / "config.yml").write_text("")

        with pytest.raises(UserConfigError, match="not a git repo"):
            set_value("docs_repo", str(non_git))

    def test_rejects_git_repo_missing_marker(self, tmp_path: Path):
        repo = tmp_path / "plain-git"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

        with pytest.raises(UserConfigError, match=r"\.task-summoner/config\.yml"):
            set_value("docs_repo", str(repo))

    def test_rejects_unknown_key(self):
        with pytest.raises(UserConfigError, match="Unknown config key"):
            set_value("bogus", "/tmp")


class TestUnsetValue:
    def test_removes_key_from_file(self, tmp_path: Path):
        repo = _make_docs_repo(tmp_path)
        set_value("docs_repo", str(repo))

        assert unset_value("docs_repo") is True

        assert json.loads(user_config_path().read_text()) == {}

    def test_returns_false_when_not_set(self):
        assert unset_value("docs_repo") is False

    def test_rejects_unknown_key(self):
        with pytest.raises(UserConfigError, match="Unknown config key"):
            unset_value("bogus")

    def test_preserves_other_keys(self, tmp_path: Path, isolated_config_dir: Path):
        # Simulate a future key in the file without bypassing validation for docs_repo.
        repo = _make_docs_repo(tmp_path)
        set_value("docs_repo", str(repo))
        raw = json.loads(user_config_path().read_text())
        raw["future_key"] = "keep-me"
        user_config_path().write_text(json.dumps(raw))

        assert unset_value("docs_repo") is True
        assert json.loads(user_config_path().read_text()) == {"future_key": "keep-me"}
