"""Async wrapper around acli CLI for Jira operations."""

from __future__ import annotations

import asyncio
import json

import structlog

from board_dispatcher.config import BoardDispatcherConfig
from board_dispatcher.models import Ticket

log = structlog.get_logger()


class JiraClient:
    def __init__(self, config: BoardDispatcherConfig) -> None:
        self._label = config.jira_label
        self._excluded_statuses = config.jira_excluded_statuses
        self._timeout = config.acli_timeout_sec

    async def search_eligible(self) -> list[Ticket]:
        """Find tickets with the claudio label assigned to me, excluding terminal statuses."""
        status_clause = ", ".join(f"'{s}'" for s in self._excluded_statuses)
        jql = (
            f"labels = '{self._label}' "
            f"AND assignee = currentUser() "
            f"AND status NOT IN ({status_clause})"
        )
        raw = await self._run_acli(
            "jira", "workitem", "search", "--jql", jql, "--limit", "50", "--json"
        )
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
        return [Ticket.from_acli_json(item) for item in items]

    async def fetch_ticket(self, key: str) -> Ticket:
        """Fetch full ticket details."""
        raw = await self._run_acli(
            "jira", "workitem", "view", key, "--fields", "*all", "--json"
        )
        data = json.loads(raw)
        return Ticket.from_acli_json(data)

    async def post_comment(self, key: str, body: str) -> str:
        """Post a comment and return the comment ID."""
        raw = await self._run_acli(
            "jira", "workitem", "comment", "create",
            "--key", key, "--body", body, "--json",
        )
        # acli returns the created comment JSON
        try:
            data = json.loads(raw)
            return str(data.get("id", ""))
        except (json.JSONDecodeError, TypeError):
            log.warning("Could not parse comment ID from acli output", ticket=key)
            return ""

    async def list_comments(self, key: str) -> list[dict]:
        """List all comments on a ticket. Returns list of {id, body, created, author}."""
        raw = await self._run_acli(
            "jira", "workitem", "comment", "list", "--key", key, "--json"
        )
        data = json.loads(raw)
        # acli wraps comments in a paginated envelope
        if isinstance(data, dict):
            return data.get("comments", [])
        if isinstance(data, list):
            return data
        return []

    async def transition(self, key: str, status: str) -> None:
        """Transition a ticket to a new status. No-op if already in that status."""
        try:
            await self._run_acli(
                "jira", "workitem", "transition", "--key", key, "--status", status, "--yes"
            )
            log.info("Ticket transitioned", ticket=key, status=status)
        except RuntimeError as e:
            log.warning("Transition failed (may already be in status)", ticket=key, status=status, error=str(e))

    async def assign(self, key: str, assignee: str = "@me") -> None:
        """Assign a ticket."""
        await self._run_acli(
            "jira", "workitem", "assign", "--key", key, "--assignee", assignee, "--yes"
        )

    async def add_label(self, key: str, label: str) -> None:
        """Add a label to a ticket."""
        await self._run_acli(
            "jira", "workitem", "edit", "--key", key, "--labels", label, "--yes"
        )

    async def set_state_label(self, key: str, state: str) -> None:
        """Set a claudio:<state> label on the ticket, removing previous state labels.

        Uses the Jira REST API directly since acli --labels replaces all labels.
        We add the new state label — old ones get cleaned up over time.
        """
        label = f"claudio:{state.lower()}"
        try:
            await self.add_label(key, label)
            log.debug("State label set", ticket=key, label=label)
        except RuntimeError as e:
            log.warning("Failed to set state label", ticket=key, label=label, error=str(e))


    async def _run_acli(self, *args: str, timeout: int | None = None) -> str:
        """Run an acli command and return stdout. Raises on failure."""
        effective_timeout = timeout or self._timeout
        cmd = ["acli", *args]
        log.debug("Running acli", cmd=" ".join(cmd))

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
            raise RuntimeError(f"acli timed out after {timeout}s: {' '.join(cmd)}")

        if proc.returncode != 0:
            err = stderr.decode().strip()
            raise RuntimeError(f"acli failed (exit {proc.returncode}): {err}")

        return stdout.decode()
