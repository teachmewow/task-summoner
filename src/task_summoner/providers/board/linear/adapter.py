"""LinearAdapter — implements BoardProvider via the Linear GraphQL API.

Linear natively supports Markdown, so no format conversion is needed for
comments or descriptions. Labels are workspace-level objects — the adapter
resolves them by name lazily and caches IDs.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import structlog

from task_summoner.models.comment import Comment
from task_summoner.models.enums import TicketState
from task_summoner.models.ticket import Ticket
from task_summoner.providers.board.linear.client import LinearClient
from task_summoner.providers.board.protocol import (
    ApprovalDecision,
    ApprovalResult,
)
from task_summoner.providers.config import LinearConfig
from task_summoner.tracker.feedback import FeedbackExtractor, ReactionDecision

log = structlog.get_logger()

_TS_TAG_PATTERN = re.compile(r"\[ts:[^\]]+\]")


class LinearAdapter:
    """BoardProvider implementation for Linear."""

    def __init__(
        self,
        config: LinearConfig,
        *,
        client: LinearClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or LinearClient(api_key=config.api_key)
        self._label_cache: dict[str, str] = {}
        self._extractor = FeedbackExtractor()

    async def search_eligible(self) -> list[Ticket]:
        query = """
        query SearchEligible($teamId: ID!, $label: String!) {
          issues(
            filter: {
              team: { id: { eq: $teamId } }
              labels: { name: { eq: $label } }
              state: { type: { nin: ["completed", "canceled"] } }
            }
            first: 50
          ) {
            nodes {
              id
              identifier
              title
              description
              state { name }
              labels { nodes { name } }
              assignee { displayName email }
            }
          }
        }
        """
        data = await self._client.query(
            query,
            {"teamId": self._config.team_id, "label": self._config.watch_label},
        )
        nodes = data.get("issues", {}).get("nodes", [])
        return [self._to_ticket(node) for node in nodes]

    async def fetch_ticket(self, ticket_id: str) -> Ticket:
        query = """
        query FetchIssue($id: String!) {
          issue(id: $id) {
            id
            identifier
            title
            description
            state { name }
            labels { nodes { name } }
            assignee { displayName email }
          }
        }
        """
        data = await self._client.query(query, {"id": ticket_id})
        node = data.get("issue")
        if not node:
            raise RuntimeError(f"Linear issue not found: {ticket_id}")
        return self._to_ticket(node)

    async def post_comment(self, ticket_id: str, body: str) -> str:
        mutation = """
        mutation CreateComment($issueId: String!, $body: String!) {
          commentCreate(input: {issueId: $issueId, body: $body}) {
            success
            comment { id }
          }
        }
        """
        issue_node_id = await self._resolve_issue_node_id(ticket_id)
        data = await self._client.query(
            mutation, {"issueId": issue_node_id, "body": body}
        )
        payload = data.get("commentCreate", {})
        if not payload.get("success"):
            raise RuntimeError(f"Linear comment create failed for {ticket_id}")
        return str(payload.get("comment", {}).get("id", ""))

    async def list_comments(self, ticket_id: str) -> list[Comment]:
        raw = await self._fetch_raw_comments(ticket_id)
        return [self._to_comment(c) for c in raw]

    async def transition(self, ticket_id: str, status: str) -> None:
        state_id = await self._resolve_state_id(status)
        if state_id is None:
            log.warning(
                "Linear state not found, skipping transition",
                ticket=ticket_id,
                status=status,
            )
            return
        issue_node_id = await self._resolve_issue_node_id(ticket_id)
        mutation = """
        mutation UpdateIssueState($id: String!, $stateId: String!) {
          issueUpdate(id: $id, input: {stateId: $stateId}) { success }
        }
        """
        await self._client.query(
            mutation, {"id": issue_node_id, "stateId": state_id}
        )
        log.info("Ticket transitioned", ticket=ticket_id, status=status)

    async def add_label(self, ticket_id: str, label: str) -> None:
        label_id = await self._resolve_or_create_label(label)
        issue_node_id = await self._resolve_issue_node_id(ticket_id)
        mutation = """
        mutation AddLabel($id: String!, $labelId: String!) {
          issueAddLabel(id: $id, labelId: $labelId) { success }
        }
        """
        await self._client.query(
            mutation, {"id": issue_node_id, "labelId": label_id}
        )

    async def remove_label(self, ticket_id: str, label: str) -> None:
        label_id = self._label_cache.get(label) or await self._resolve_label_id(label)
        if not label_id:
            return
        issue_node_id = await self._resolve_issue_node_id(ticket_id)
        mutation = """
        mutation RemoveLabel($id: String!, $labelId: String!) {
          issueRemoveLabel(id: $id, labelId: $labelId) { success }
        }
        """
        await self._client.query(
            mutation, {"id": issue_node_id, "labelId": label_id}
        )

    async def assign(self, ticket_id: str, assignee: str | None) -> None:
        issue_node_id = await self._resolve_issue_node_id(ticket_id)
        assignee_id = await self._resolve_user_id(assignee) if assignee else None
        mutation = """
        mutation UpdateAssignee($id: String!, $assigneeId: String) {
          issueUpdate(id: $id, input: {assigneeId: $assigneeId}) { success }
        }
        """
        await self._client.query(
            mutation, {"id": issue_node_id, "assigneeId": assignee_id}
        )

    async def set_state_label(self, ticket_id: str, state: TicketState) -> None:
        label = f"ts:{state.value.lower()}"
        try:
            await self.add_label(ticket_id, label)
            log.debug("State label set", ticket=ticket_id, label=label)
        except Exception as e:
            log.warning(
                "Failed to set state label",
                ticket=ticket_id,
                label=label,
                error=str(e),
            )

    async def get_comment_replies(
        self, ticket_id: str, after_comment_id: str
    ) -> list[Comment]:
        raw = await self._fetch_raw_comments(ticket_id)
        anchor = next((c for c in raw if c.get("id") == after_comment_id), None)
        if anchor is None:
            return []
        anchor_ts = self._parse_timestamp_str(anchor.get("createdAt"))
        replies: list[dict] = []
        for c in raw:
            if c.get("id") == after_comment_id:
                continue
            ts = self._parse_timestamp_str(c.get("createdAt"))
            if ts > anchor_ts:
                replies.append(c)
        return [self._to_comment(c) for c in replies]

    async def post_tagged_comment(
        self, ticket_id: str, tag: str, body: str
    ) -> str:
        tagged_body = f"{body}\n\n{tag}"
        return await self.post_comment(ticket_id, tagged_body)

    async def check_approval(
        self, ticket_id: str, comment_id: str
    ) -> ApprovalResult:
        if not comment_id:
            return ApprovalResult(decision=ApprovalDecision.PENDING)

        replies = await self.get_comment_replies(ticket_id, comment_id)
        if not replies:
            return ApprovalResult(decision=ApprovalDecision.PENDING)

        for reply in reversed(replies):
            if reply.is_bot or _TS_TAG_PATTERN.search(reply.body):
                continue
            result = self._extractor.extract(reply.body)
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

    async def _fetch_raw_comments(self, ticket_id: str) -> list[dict[str, Any]]:
        query = """
        query ListComments($id: String!) {
          issue(id: $id) {
            comments(first: 100) {
              nodes {
                id
                body
                createdAt
                user { displayName email }
              }
            }
          }
        }
        """
        data = await self._client.query(query, {"id": ticket_id})
        issue = data.get("issue") or {}
        return issue.get("comments", {}).get("nodes", [])

    async def _resolve_issue_node_id(self, ticket_id: str) -> str:
        """Linear accepts either UUID or identifier (e.g. ENG-123). Return whichever was provided."""
        return ticket_id

    async def _resolve_state_id(self, status: str) -> str | None:
        query = """
        query TeamStates($teamId: String!) {
          team(id: $teamId) {
            states { nodes { id name } }
          }
        }
        """
        data = await self._client.query(query, {"teamId": self._config.team_id})
        nodes = (data.get("team") or {}).get("states", {}).get("nodes", [])
        for node in nodes:
            if node.get("name", "").lower() == status.lower():
                return str(node.get("id"))
        return None

    async def _resolve_label_id(self, name: str) -> str | None:
        query = """
        query TeamLabels($teamId: String!) {
          team(id: $teamId) {
            labels(first: 250) { nodes { id name } }
          }
        }
        """
        data = await self._client.query(query, {"teamId": self._config.team_id})
        nodes = (data.get("team") or {}).get("labels", {}).get("nodes", [])
        for node in nodes:
            if node.get("name") == name:
                label_id = str(node.get("id"))
                self._label_cache[name] = label_id
                return label_id
        return None

    async def _resolve_or_create_label(self, name: str) -> str:
        cached = self._label_cache.get(name)
        if cached:
            return cached
        existing = await self._resolve_label_id(name)
        if existing:
            return existing
        mutation = """
        mutation CreateLabel($teamId: String!, $name: String!) {
          issueLabelCreate(input: {teamId: $teamId, name: $name}) {
            success
            issueLabel { id }
          }
        }
        """
        data = await self._client.query(
            mutation, {"teamId": self._config.team_id, "name": name}
        )
        payload = data.get("issueLabelCreate", {})
        if not payload.get("success"):
            raise RuntimeError(f"Linear label create failed: {name}")
        label_id = str(payload.get("issueLabel", {}).get("id", ""))
        self._label_cache[name] = label_id
        return label_id

    async def _resolve_user_id(self, identifier: str) -> str | None:
        query = """
        query FindUser($identifier: String!) {
          users(filter: {or: [
            {email: {eq: $identifier}},
            {displayName: {eq: $identifier}}
          ]}, first: 1) {
            nodes { id }
          }
        }
        """
        data = await self._client.query(query, {"identifier": identifier})
        nodes = data.get("users", {}).get("nodes", [])
        if nodes:
            return str(nodes[0].get("id"))
        return None

    def _to_ticket(self, node: dict[str, Any]) -> Ticket:
        identifier = node.get("identifier", "")
        labels = [
            label.get("name", "")
            for label in (node.get("labels") or {}).get("nodes", [])
            if label.get("name")
        ]
        assignee_node = node.get("assignee") or {}
        assignee = assignee_node.get("displayName") or assignee_node.get("email")
        state_name = (node.get("state") or {}).get("name", "")
        return Ticket(
            key=identifier,
            summary=node.get("title", ""),
            description=node.get("description") or "",
            status=state_name,
            labels=labels,
            assignee=assignee,
            raw=node,
        )

    def _to_comment(self, raw: dict[str, Any]) -> Comment:
        user = raw.get("user") or {}
        body = str(raw.get("body", ""))
        author = user.get("displayName") or user.get("email") or ""
        return Comment(
            id=str(raw.get("id", "")),
            author=author,
            body=body,
            created_at=self._parse_timestamp_str(raw.get("createdAt")),
            is_bot=bool(_TS_TAG_PATTERN.search(body)),
            provider_data=raw,
        )

    def _parse_timestamp_str(self, value: Any) -> datetime:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.min
