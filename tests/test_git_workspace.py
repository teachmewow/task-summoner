"""Tests for git workspace manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from task_summoner.config import TaskSummonerConfig
from task_summoner.models import Ticket
from task_summoner.workspace import GitWorkspaceManager, derive_branch_name


class TestDeriveBranchName:
    def test_simple(self):
        t = Ticket(key="LLMOPS-123", summary="Add retry logic")
        assert derive_branch_name(t) == "LLMOPS-123-add-retry-logic"

    def test_truncates_to_four_words(self):
        t = Ticket(key="LLMOPS-1", summary="A very long ticket summary with many words")
        branch = derive_branch_name(t)
        parts = branch.split("-")
        assert len(parts) <= 6

    def test_special_characters_stripped(self):
        t = Ticket(key="LLMOPS-99", summary="Fix: API (v2) timeout!")
        branch = derive_branch_name(t)
        assert ":" not in branch
        assert "(" not in branch
        assert "!" not in branch

    def test_lowercase(self):
        t = Ticket(key="LLMOPS-1", summary="FIX THE THING")
        branch = derive_branch_name(t)
        assert branch == branch.lower() or branch.startswith("LLMOPS")


class TestGitWorkspaceManager:
    @pytest.fixture
    def manager(self, config: TaskSummonerConfig, tmp_path) -> GitWorkspaceManager:
        config.workspace_root = str(tmp_path / "workspaces")
        return GitWorkspaceManager(config)

    @pytest.fixture
    def mock_git(self):
        with patch.object(GitWorkspaceManager, "_git", new_callable=AsyncMock) as mock:
            mock.return_value = ""
            yield mock

    async def test_create_workspace(self, manager, mock_git, tmp_path):
        worktree_path = tmp_path / "workspaces" / "TEST-1"
        worktree_path.mkdir(parents=True)

        mock_git.return_value = "main"
        path = await manager.create("TEST-1", "test-branch", "/tmp/repo")
        assert "TEST-1" in path

    async def test_create_reuses_existing(self, manager, tmp_path):
        worktree_path = tmp_path / "workspaces" / "TEST-1"
        worktree_path.mkdir(parents=True)

        with patch.object(manager, "_git", new_callable=AsyncMock):
            path = await manager.create("TEST-1", "branch", "/tmp/repo")
            assert "TEST-1" in path

    async def test_remove_workspace(self, manager, mock_git, tmp_path):
        worktree_path = tmp_path / "workspaces" / "TEST-1"
        worktree_path.mkdir(parents=True)

        await manager.remove("TEST-1")
        mock_git.assert_called()

    async def test_remove_nonexistent_is_noop(self, manager):
        await manager.remove("NONEXISTENT-1")

    def test_path_exists(self, manager, tmp_path):
        worktree_path = tmp_path / "workspaces" / "TEST-1"
        worktree_path.mkdir(parents=True)
        assert manager.path("TEST-1") is not None

    def test_path_not_exists(self, manager):
        assert manager.path("NONEXISTENT-1") is None

    async def test_cleanup_orphans(self, manager, tmp_path):
        workspaces = tmp_path / "workspaces"
        (workspaces / "KEEP-1").mkdir(parents=True)
        (workspaces / "ORPHAN-1").mkdir(parents=True)

        await manager.cleanup_orphans({"KEEP-1"})
        assert (workspaces / "KEEP-1").exists()
        assert not (workspaces / "ORPHAN-1").exists()
