"""Git worktree lifecycle manager — one workspace per ticket."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

import structlog

from task_summoner.config import TaskSummonerConfig
from task_summoner.models import Ticket

log = structlog.get_logger()


class GitWorkspaceManager:
    def __init__(self, config: TaskSummonerConfig) -> None:
        self._config = config
        self._root = Path(config.workspace_root)
        self._timeout = config.git_timeout_sec
        self._root.mkdir(parents=True, exist_ok=True)

    async def create(self, ticket_key: str, branch_name: str, repo_path: str) -> str:
        """Create a git worktree for a ticket.

        1. Fetch latest from origin
        2. Create worktree on a new branch from origin/main
        Returns the absolute worktree path.
        """
        worktree_path = self._root / ticket_key

        if worktree_path.exists():
            log.info("Worktree already exists, reusing", ticket=ticket_key, path=str(worktree_path))
            return str(worktree_path)

        # Fetch latest
        await self._git(repo_path, "fetch", "origin")

        # Detect default branch
        base_branch = await self._detect_base_branch(repo_path)

        # Create worktree with new branch
        await self._git(
            repo_path, "worktree", "add",
            str(worktree_path), "-b", branch_name, f"origin/{base_branch}",
        )

        log.info(
            "Worktree created",
            ticket=ticket_key,
            branch=branch_name,
            base=base_branch,
            path=str(worktree_path),
        )
        return str(worktree_path)

    async def recover(self, ticket_key: str, branch_name: str, repo_path: str) -> str:
        """Recover a worktree from an existing branch.

        Used when the worktree directory was lost (e.g., /tmp cleaned on reboot)
        but the branch still exists locally or on the remote.

        Runs `git worktree prune` first to clear stale worktree references
        that point to directories that no longer exist.
        """
        worktree_path = self._root / ticket_key

        if worktree_path.exists():
            return str(worktree_path)

        await self._git(repo_path, "fetch", "origin")

        # Prune stale worktree entries — the old worktree dir was deleted
        # but git still thinks the branch is checked out there.
        await self._git(repo_path, "worktree", "prune")

        # Try attaching to the existing local branch
        try:
            await self._git(
                repo_path, "worktree", "add",
                str(worktree_path), branch_name,
            )
            log.info(
                "Worktree recovered from local branch",
                ticket=ticket_key, branch=branch_name,
            )
            return str(worktree_path)
        except RuntimeError:
            pass

        # Branch doesn't exist locally — create from remote tracking branch
        try:
            await self._git(
                repo_path, "worktree", "add",
                str(worktree_path), "-b", branch_name, f"origin/{branch_name}",
            )
            log.info(
                "Worktree recovered from remote branch",
                ticket=ticket_key, branch=branch_name,
            )
            return str(worktree_path)
        except RuntimeError as e:
            raise RuntimeError(
                f"Cannot recover worktree for {ticket_key}: branch '{branch_name}' "
                f"not found locally or on remote. Error: {e}"
            )

    async def remove(self, ticket_key: str) -> None:
        """Remove a worktree for a ticket."""
        worktree_path = self._root / ticket_key
        if not worktree_path.exists():
            return

        # Find the base repo that owns this worktree
        # git worktree remove needs to run from the main repo
        # We can use the worktree path itself with --force
        try:
            await self._git(str(worktree_path), "worktree", "remove", str(worktree_path), "--force")
        except RuntimeError:
            # Fallback: just remove the directory and let git prune later
            shutil.rmtree(worktree_path, ignore_errors=True)
            log.warning("Force-removed worktree directory", ticket=ticket_key)

        log.info("Worktree removed", ticket=ticket_key)

    def path(self, ticket_key: str) -> str | None:
        """Return worktree path if it exists, None otherwise."""
        p = self._root / ticket_key
        return str(p) if p.exists() else None

    async def cleanup_orphans(self, active_keys: set[str]) -> None:
        """Remove worktrees that have no matching active ticket."""
        if not self._root.exists():
            return
        for item in self._root.iterdir():
            if item.is_dir() and item.name not in active_keys:
                log.info("Cleaning up orphan worktree", name=item.name)
                shutil.rmtree(item, ignore_errors=True)

    async def _detect_base_branch(self, repo_path: str) -> str:
        """Detect if the repo uses 'main' or 'master'."""
        try:
            await self._git(repo_path, "rev-parse", "--verify", "origin/main")
            return "main"
        except RuntimeError:
            return "master"

    async def _git(self, cwd: str, *args: str, timeout: int | None = None) -> str:
        """Run a git command and return stdout."""
        effective_timeout = timeout or self._timeout
        cmd = ["git", "-C", cwd, *args]
        log.debug("Running git", cmd=" ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"git timed out after {effective_timeout}s: {' '.join(cmd)}")

        if proc.returncode != 0:
            err = stderr.decode().strip()
            raise RuntimeError(f"git failed (exit {proc.returncode}): {err}")

        return stdout.decode().strip()


def derive_branch_name(ticket: Ticket) -> str:
    """Derive a branch name from a ticket: {KEY}-{2-4-word-slug}."""
    slug = ticket.summary.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    words = slug.split("-")[:4]
    return f"{ticket.key}-{'-'.join(words)}"
