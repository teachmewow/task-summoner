"""Base state classes and services container."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import structlog

from board_dispatcher.config import AgentConfig, BoardDispatcherConfig
from board_dispatcher.models import Ticket, TicketContext, TicketState, branch_from_labels
from board_dispatcher.tracker import Adf, MessageTag, ReactionDecision, ReactionResult, check_reaction, find_bd_comment, find_latest_bd_tag

log = structlog.get_logger()


class StateServices:
    """Dependency container passed to state handlers."""

    def __init__(self, jira, workspace, agent_runner, store) -> None:
        self.jira = jira
        self.workspace = workspace
        self.agent_runner = agent_runner
        self.store = store


class BaseState(ABC):
    """Base class for all state handlers."""

    def __init__(self, config: BoardDispatcherConfig) -> None:
        self._config = config

    @property
    @abstractmethod
    def state(self) -> TicketState:
        ...

    @property
    def requires_agent(self) -> bool:
        return False

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def agent_config(self) -> AgentConfig | None:
        return None

    @abstractmethod
    async def handle(
        self, ctx: TicketContext, ticket: Ticket, services: StateServices
    ) -> str:
        ...

    async def _ensure_workspace(
        self, ctx: TicketContext, ticket: Ticket, svc: StateServices
    ) -> str:
        """Ensure the workspace directory exists, recovering if needed.

        If the worktree was lost (e.g., /tmp cleaned on reboot), recreate it
        from the existing branch on the remote.
        """
        if ctx.workspace_path and Path(ctx.workspace_path).exists():
            return ctx.workspace_path

        if not ctx.branch_name:
            # Recover branch name from Jira labels
            branch = branch_from_labels(ticket.labels)
            if branch:
                ctx.branch_name = branch
                log.info("Recovered branch from Jira label", ticket=ticket.key, branch=branch)
            else:
                raise RuntimeError(
                    f"Cannot recover workspace for {ticket.key}: no branch_name in context or Jira labels"
                )

        repo_name, repo_path = self._config.resolve_repo(ticket.labels)
        log.warning(
            "Workspace missing, recovering",
            ticket=ticket.key,
            branch=ctx.branch_name,
            old_path=ctx.workspace_path,
        )

        workspace = await svc.workspace.recover(ticket.key, ctx.branch_name, repo_path)
        ctx.workspace_path = workspace
        return workspace

    def _artifact_dir(self, ticket_key: str) -> Path:
        d = Path(self._config.artifacts_dir).resolve() / ticket_key
        d.mkdir(parents=True, exist_ok=True)
        return d


class BaseApprovalState(BaseState):
    """Base class for all approval-waiting states (✅ or 🔄 pattern).

    Subclasses define:
    - comment_meta_key: metadata key holding the bd tag string to poll
    - trigger_on_approve: trigger when human replies "lgtm"/"approved"
    - trigger_on_retry: trigger when human replies "retry"/"fix"
    """

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    @abstractmethod
    def comment_meta_key(self) -> str:
        """Metadata key where the polled comment ID is stored."""
        ...

    @property
    @abstractmethod
    def trigger_on_approve(self) -> str:
        ...

    @property
    @abstractmethod
    def trigger_on_retry(self) -> str:
        ...

    @property
    @abstractmethod
    def bd_tag_state(self) -> str:
        """The state name used in the bd tag (e.g., 'implementing' for mr_comment_id)."""
        ...

    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        comment_id = ctx.get_meta(self.comment_meta_key)
        comments = await svc.jira.list_comments(ticket.key)

        # Recover or re-recover if the stored tag no longer exists in comments
        needs_recovery = not comment_id
        if comment_id:
            if find_bd_comment(comments, comment_id) is None:
                log.warning("Stored bd tag not found in comments (deleted?), recovering", ticket=ticket.key)
                needs_recovery = True

        if needs_recovery:
            comment_id = find_latest_bd_tag(comments, ticket.key, self.bd_tag_state)
            if comment_id:
                ctx.set_meta(self.comment_meta_key, comment_id)
                log.info("Recovered bd tag from Jira comments", ticket=ticket.key, tag=comment_id)
            else:
                log.warning("No bd tag found in comments", ticket=ticket.key, state=self.bd_tag_state)
                return "_wait"

        result = await check_reaction(svc.jira, ticket.key, comment_id, comments=comments)

        # Store reviewer feedback for the next handler to consume
        if result.has_feedback:
            ctx.set_meta("reviewer_feedback", result.feedback)
            log.info("Reviewer feedback captured", ticket=ticket.key, feedback=result.feedback[:100])
        else:
            ctx.set_meta("reviewer_feedback", "")

        match result.decision:
            case ReactionDecision.APPROVED:
                ctx.retry_count = 0
                return self.trigger_on_approve
            case ReactionDecision.RETRY:
                # Post "On it..." with new bd tag to anchor the next approval check.
                # Without this, the old "retry" reply stays after the original tag
                # and gets detected again on the next poll → infinite retry loop.
                ack_tag = MessageTag(ticket_key=ticket.key, state=self.bd_tag_state)
                ack = ack_tag.embed_in_adf(
                    Adf.paragraph("On it... processing feedback."),
                )
                await svc.jira.post_comment(ticket.key, ack)
                ctx.set_meta(self.comment_meta_key, ack_tag.tag)
                return self.trigger_on_retry
            case ReactionDecision.WAITING:
                return "_wait"
