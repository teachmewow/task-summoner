"""End-to-end tests for the ``task-summoner config`` subcommands."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from task_summoner.__main__ import main
from task_summoner.cli_config import (
    cmd_config_get,
    cmd_config_list,
    cmd_config_set,
    cmd_config_unset,
)
from task_summoner.user_config import user_config_path


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.delenv("TASK_SUMMONER_DOCS_REPO", raising=False)
    return xdg


def _make_docs_repo(root: Path, name: str = "docs-repo") -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".task-summoner").mkdir()
    (repo / ".task-summoner" / "config.yml").write_text("version: 1\n")
    return repo


class TestCmdConfigGet:
    def test_unset_prints_unset_and_exits_1(self, capsys):
        rc = cmd_config_get("docs_repo")

        captured = capsys.readouterr()
        assert rc == 1
        assert "docs_repo" in captured.out
        assert "unset" in captured.out

    def test_set_via_file_prints_file_source_and_exits_0(self, tmp_path: Path, capsys):
        repo = _make_docs_repo(tmp_path)
        cmd_config_set("docs_repo", str(repo))
        capsys.readouterr()  # drain

        rc = cmd_config_get("docs_repo")

        captured = capsys.readouterr()
        assert rc == 0
        assert str(repo) in captured.out
        assert "source: file" in captured.out

    def test_env_override_reports_env_source(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        repo = _make_docs_repo(tmp_path)
        cmd_config_set("docs_repo", str(repo))
        capsys.readouterr()

        monkeypatch.setenv("TASK_SUMMONER_DOCS_REPO", "/override/path")
        rc = cmd_config_get("docs_repo")

        captured = capsys.readouterr()
        assert rc == 0
        assert "/override/path" in captured.out
        assert "source: env" in captured.out

    def test_unknown_key_exits_2(self, capsys):
        rc = cmd_config_get("bogus")

        captured = capsys.readouterr()
        assert rc == 2
        assert "Unknown config key" in captured.err


class TestCmdConfigSet:
    def test_writes_file_and_exits_0(self, tmp_path: Path, capsys):
        repo = _make_docs_repo(tmp_path)

        rc = cmd_config_set("docs_repo", str(repo))

        captured = capsys.readouterr()
        assert rc == 0
        assert json.loads(user_config_path().read_text()) == {"docs_repo": str(repo)}
        assert f"Set docs_repo = {repo}" in captured.out
        assert "TASK_SUMMONER_DOCS_REPO" in captured.out

    def test_relative_path_actionable_error(self, capsys):
        rc = cmd_config_set("docs_repo", "relative/path")

        captured = capsys.readouterr()
        assert rc == 1
        assert "absolute" in captured.err

    def test_nonexistent_path_mentions_template(self, tmp_path: Path, capsys):
        missing = tmp_path / "nope"

        rc = cmd_config_set("docs_repo", str(missing))

        captured = capsys.readouterr()
        assert rc == 1
        assert "does not exist" in captured.err
        assert "task-summoner-docs-template" in captured.err

    def test_non_git_dir_mentions_template(self, tmp_path: Path, capsys):
        plain = tmp_path / "plain"
        plain.mkdir()

        rc = cmd_config_set("docs_repo", str(plain))

        captured = capsys.readouterr()
        assert rc == 1
        assert "not a git repo" in captured.err
        assert "task-summoner-docs-template" in captured.err

    def test_missing_marker_mentions_eng93(self, tmp_path: Path, capsys):
        repo = tmp_path / "bare-git"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

        rc = cmd_config_set("docs_repo", str(repo))

        captured = capsys.readouterr()
        assert rc == 1
        assert ".task-summoner/config.yml" in captured.err
        assert "ENG-93" in captured.err


class TestCmdConfigUnset:
    def test_removes_set_key(self, tmp_path: Path, capsys):
        repo = _make_docs_repo(tmp_path)
        cmd_config_set("docs_repo", str(repo))
        capsys.readouterr()

        rc = cmd_config_unset("docs_repo")

        captured = capsys.readouterr()
        assert rc == 0
        assert "Unset docs_repo" in captured.out
        assert json.loads(user_config_path().read_text()) == {}

    def test_no_op_when_missing(self, capsys):
        rc = cmd_config_unset("docs_repo")

        captured = capsys.readouterr()
        assert rc == 0
        assert "was not set" in captured.out


class TestCmdConfigList:
    def test_lists_all_keys_with_sources(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        # docs_repo: file
        repo = _make_docs_repo(tmp_path)
        cmd_config_set("docs_repo", str(repo))
        capsys.readouterr()

        rc = cmd_config_list()

        captured = capsys.readouterr()
        assert rc == 0
        assert "docs_repo" in captured.out
        assert str(repo) in captured.out
        assert "TASK_SUMMONER_DOCS_REPO" in captured.out

    def test_shows_unset_when_nothing_set(self, capsys):
        rc = cmd_config_list()

        captured = capsys.readouterr()
        assert rc == 0
        assert "unset" in captured.out


class TestMainDispatch:
    """Integration: go through argparse / ``main`` like the user would."""

    def test_config_get_exits_1_when_unset(self, capsys):
        with patch("sys.argv", ["task-summoner", "config", "get", "docs_repo"]):
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "unset" in captured.out

    def test_config_set_then_get_roundtrip(self, tmp_path: Path, capsys):
        repo = _make_docs_repo(tmp_path)

        with patch("sys.argv", ["task-summoner", "config", "set", "docs_repo", str(repo)]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0

        capsys.readouterr()

        with patch("sys.argv", ["task-summoner", "config", "get", "docs_repo"]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0

        captured = capsys.readouterr()
        assert str(repo) in captured.out

    def test_config_list_runs(self, capsys):
        with patch("sys.argv", ["task-summoner", "config", "list"]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0

        captured = capsys.readouterr()
        assert "docs_repo" in captured.out

    def test_config_unset_roundtrip(self, tmp_path: Path, capsys):
        repo = _make_docs_repo(tmp_path)
        with patch("sys.argv", ["task-summoner", "config", "set", "docs_repo", str(repo)]):
            with pytest.raises(SystemExit):
                main()
        capsys.readouterr()

        with patch("sys.argv", ["task-summoner", "config", "unset", "docs_repo"]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0

        captured = capsys.readouterr()
        assert "Unset docs_repo" in captured.out
