"""JiraAdapter — implements BoardProvider by delegating to acli-based JiraClient.

Converts between the provider-agnostic models (Ticket, Comment, ApprovalResult) and
Jira-native formats (ADF, acli JSON). Core never sees ADF or Jira-specific shapes.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog

from task_summoner.models.comment import Comment
from task_summoner.models.enums import TicketState
from task_summoner.models.ticket import Ticket
from task_summoner.providers.board.protocol import (
    ApprovalDecision,
    ApprovalResult,
    BoardNotFoundError,
)
from task_summoner.providers.config import JiraConfig
from task_summoner.tracker.feedback import (
    FeedbackExtractor,
    ReactionDecision,
)
from task_summoner.tracker.message_tracker import (
    get_replies_after,
    is_ts_comment,
)
from task_summoner.utils import run_cli

log = structlog.get_logger()

_DEFAULT_TIMEOUT_SEC = 30
_DEFAULT_EXCLUDED_STATUSES = ["Done", "Cancelled", "Closed"]


class JiraAdapter:
    """BoardProvider implementation backed by the acli CLI tool."""

    def __init__(
        self,
        config: JiraConfig,
        *,
        timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
        excluded_statuses: list[str] | None = None,
    ) -> None:
        self._config = config
        self._timeout_sec = timeout_sec
        self._excluded_statuses = excluded_statuses or _DEFAULT_EXCLUDED_STATUSES
        self._extractor = FeedbackExtractor()

    async def search_eligible(self) -> list[Ticket]:
        status_clause = ", ".join(f"'{s}'" for s in self._excluded_statuses)
        jql = (
            f"labels = '{self._config.watch_label}' "
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

    async def fetch_ticket(self, ticket_id: str) -> Ticket:
        try:
            raw = await self._run_acli(
                "jira", "workitem", "view", ticket_id, "--fields", "*all", "--json"
            )
        except RuntimeError as e:
            if _is_not_found_error(str(e)):
                raise BoardNotFoundError(f"Jira issue not found: {ticket_id}") from e
            raise
        data = json.loads(raw)
        return Ticket.from_acli_json(data)

    async def post_comment(self, ticket_id: str, body: str) -> str:
        adf_body = self._markdown_to_adf_json(body)
        raw = await self._run_acli(
            "jira",
            "workitem",
            "comment",
            "create",
            "--key",
            ticket_id,
            "--body",
            adf_body,
            "--json",
        )
        try:
            data = json.loads(raw)
            return str(data.get("id", ""))
        except (json.JSONDecodeError, TypeError):
            log.warning("Could not parse comment ID", ticket=ticket_id)
            return ""

    async def list_comments(self, ticket_id: str) -> list[Comment]:
        raw_comments = await self._raw_list_comments(ticket_id)
        return [self._to_comment(c) for c in raw_comments]

    async def transition(self, ticket_id: str, status: str) -> None:
        try:
            await self._run_acli(
                "jira",
                "workitem",
                "transition",
                "--key",
                ticket_id,
                "--status",
                status,
                "--yes",
            )
            log.info("Ticket transitioned", ticket=ticket_id, status=status)
        except RuntimeError as e:
            log.warning(
                "Transition failed (may already be in status)",
                ticket=ticket_id,
                status=status,
                error=str(e),
            )

    async def add_label(self, ticket_id: str, label: str) -> None:
        await self._run_acli(
            "jira",
            "workitem",
            "edit",
            "--key",
            ticket_id,
            "--labels",
            label,
            "--yes",
        )

    async def remove_label(self, ticket_id: str, label: str) -> None:
        await self._run_acli(
            "jira",
            "workitem",
            "edit",
            "--key",
            ticket_id,
            "--remove-labels",
            label,
            "--yes",
        )

    async def assign(self, ticket_id: str, assignee: str | None) -> None:
        target = assignee or "none"
        await self._run_acli(
            "jira",
            "workitem",
            "assign",
            "--key",
            ticket_id,
            "--assignee",
            target,
            "--yes",
        )

    async def set_state_label(self, ticket_id: str, state: TicketState) -> None:
        label = f"ts:{state.value.lower()}"
        try:
            await self.add_label(ticket_id, label)
            log.debug("State label set", ticket=ticket_id, label=label)
        except RuntimeError as e:
            log.warning(
                "Failed to set state label",
                ticket=ticket_id,
                label=label,
                error=str(e),
            )

    async def get_comment_replies(self, ticket_id: str, after_comment_id: str) -> list[Comment]:
        raw_comments = await self._raw_list_comments(ticket_id)
        replies = get_replies_after(raw_comments, after_comment_id)
        return [self._to_comment(c) for c in replies]

    async def post_tagged_comment(self, ticket_id: str, tag: str, body: str) -> str:
        """Post a comment with an embedded tag. Returns the tag itself, which is the
        robust approval-tracking identifier (native IDs don't survive state recovery)."""
        tagged_body = f"{body}\n\n{tag}"
        await self.post_comment(ticket_id, tagged_body)
        return tag

    async def check_approval(self, ticket_id: str, comment_id: str) -> ApprovalResult:
        if not comment_id:
            return ApprovalResult(decision=ApprovalDecision.PENDING)

        raw_comments = await self._raw_list_comments(ticket_id)
        if not raw_comments:
            return ApprovalResult(decision=ApprovalDecision.PENDING)

        replies = get_replies_after(raw_comments, comment_id)
        if not replies:
            return ApprovalResult(decision=ApprovalDecision.PENDING)

        for reply in reversed(replies):
            if is_ts_comment(reply):
                continue
            body = str(reply.get("body", ""))
            result = self._extractor.extract(body)
            if result.decision == ReactionDecision.APPROVED:
                return ApprovalResult(
                    decision=ApprovalDecision.APPROVED,
                    feedback=result.feedback or None,
                )
            if result.decision == ReactionDecision.RETRY:
                return ApprovalResult(
                    decision=ApprovalDecision.RETRY,
                    feedback=result.feedback or None,
                )

        return ApprovalResult(decision=ApprovalDecision.PENDING)

    async def _raw_list_comments(self, ticket_id: str) -> list[dict]:
        raw = await self._run_acli(
            "jira", "workitem", "comment", "list", "--key", ticket_id, "--json"
        )
        data = json.loads(raw)
        if isinstance(data, dict):
            return data.get("comments", [])
        if isinstance(data, list):
            return data
        return []

    def _to_comment(self, raw: dict[str, Any]) -> Comment:
        body = str(raw.get("body", ""))
        return Comment(
            id=str(raw.get("id", "")),
            author=self._extract_author(raw),
            body=body,
            created_at=self._parse_timestamp(raw),
            is_bot=is_ts_comment(raw),
            provider_data=raw,
        )

    def _extract_author(self, raw: dict[str, Any]) -> str:
        author = raw.get("author") or raw.get("updateAuthor")
        if isinstance(author, dict):
            return (
                author.get("displayName")
                or author.get("emailAddress")
                or author.get("accountId")
                or ""
            )
        if isinstance(author, str):
            return author
        return ""

    def _parse_timestamp(self, raw: dict[str, Any]) -> datetime:
        for key in ("created", "createdAt", "updated"):
            value = raw.get(key)
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    continue
        return datetime.now()

    def _markdown_to_adf_json(self, body: str) -> str:
        from task_summoner.tracker.adf import AdfDocument
        from task_summoner.tracker.adf_converter import markdown_to_adf

        nodes = markdown_to_adf(body)
        return AdfDocument(content=nodes).to_json()

    async def _run_acli(self, *args: str) -> str:
        return await run_cli(["acli", *args], timeout_sec=self._timeout_sec)


def _is_not_found_error(error_message: str) -> bool:
    """Detect acli/Jira signals that a ticket does not exist."""
    needles = ("does not exist", "not found", "no such issue")
    lowered = error_message.lower()
    return any(n in lowered for n in needles)
