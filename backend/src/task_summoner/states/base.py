"""Base state classes and services container."""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import structlog

from task_summoner.config import AgentConfig, TaskSummonerConfig
from task_summoner.models import CostEntry, Ticket, TicketContext, TicketState, branch_from_labels
from task_summoner.providers.agent import AgentProfile, AgentProvider, AgentResult
from task_summoner.providers.board import (
    ApprovalDecision,
    BoardProvider,
)

log = structlog.get_logger()


class WorkspaceService(Protocol):
    async def create(self, ticket_key: str, branch: str, repo_path: str) -> str: ...
    async def recover(self, ticket_key: str, branch: str, repo_path: str) -> str: ...


class _StateStoreProtocol(Protocol):
    def save(self, ctx: TicketContext) -> None: ...
    def load(self, ticket_key: str) -> TicketContext | None: ...


class _StreamWriterProtocol(Protocol):
    """Minimal shape the agent-event stream writer exposes to state handlers.

    Kept as a protocol (not the concrete class) so tests can mock with
    ``AsyncMock`` / plain callables without dragging the filesystem in.
    """

    def record(self, event, *, agent_name: str | None = ..., state: str | None = ...) -> None: ...
    def close(self) -> None: ...


@dataclass
class StateServices:
    """Dependency container passed to state handlers.

    All handlers interact with providers through abstract contracts
    (BoardProvider, AgentProvider). No direct imports of Jira/Claude SDK.
    """

    board: BoardProvider
    workspace: WorkspaceService
    agent: AgentProvider
    store: _StateStoreProtocol
    # Optional factory for the per-ticket stream writer. When set, each
    # ``_run_agent`` call installs an event_callback that persists the
    # adapter's AgentEvents to ``artifacts/{KEY}/stream.jsonl`` and fans
    # them out to live SSE subscribers. Left optional so tests that mock
    # StateServices keep working unchanged.
    stream_writer_factory: Callable[[str], _StreamWriterProtocol] | None = field(default=None)


def agent_profile_from_config(name: str, config: AgentConfig) -> AgentProfile:
    """Translate the legacy AgentConfig into the provider-agnostic AgentProfile."""
    return AgentProfile(
        name=name,
        model=config.model,
        max_turns=config.max_turns,
        max_cost_usd=config.max_budget_usd,
        tools=list(config.tools),
    )


class BaseState(ABC):
    """Base class for all state handlers."""

    def __init__(self, config: TaskSummonerConfig) -> None:
        self._config = config

    @property
    @abstractmethod
    def state(self) -> TicketState: ...

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
    async def handle(self, ctx: TicketContext, ticket: Ticket, services: StateServices) -> str: ...

    async def _ensure_workspace(
        self, ctx: TicketContext, ticket: Ticket, svc: StateServices
    ) -> str:
        """Ensure the workspace directory exists, recovering if needed."""
        if ctx.workspace_path and Path(ctx.workspace_path).exists():
            return ctx.workspace_path

        if not ctx.branch_name:
            branch = branch_from_labels(ticket.labels)
            if branch:
                ctx.branch_name = branch
                log.info("Recovered branch from label", ticket=ticket.key, branch=branch)
            else:
                raise RuntimeError(
                    f"Cannot recover workspace for {ticket.key}: "
                    "no branch_name in context or board labels"
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

    async def _run_agent(
        self,
        svc: StateServices,
        agent_name: str,
        prompt: str,
        workspace: str,
        ctx: TicketContext | None = None,
    ) -> AgentResult:
        """Invoke the agent provider. If `ctx` is given, also records cost_history.

        When `svc.stream_writer_factory` is configured, install an event
        callback that persists every AgentEvent emitted by the adapter to
        ``artifacts/{KEY}/stream.jsonl`` — that is the transcript the
        dashboard timeline replays + tails. The writer is scoped to the
        ticket, not the state handler, so multi-state dispatches append to
        a single file (planning → implementing → fixing_mr all in one log).
        """
        profile = agent_profile_from_config(agent_name, self.agent_config or AgentConfig())

        writer = None
        event_callback = None
        factory = svc.stream_writer_factory
        if factory is not None and ctx is not None:
            try:
                writer = factory(ctx.ticket_key)
            except Exception:  # defensive: streaming must never block dispatch
                log.exception("stream_writer.factory_failed", ticket=ctx.ticket_key)
                writer = None
            if writer is not None:
                state_value = self.state.value

                def event_callback(event, _writer=writer, _agent=agent_name, _state=state_value):
                    try:
                        _writer.record(event, agent_name=_agent, state=_state)
                    except Exception:
                        log.exception("stream_writer.record_failed", ticket=ctx.ticket_key)

        try:
            result = await svc.agent.run(
                prompt=prompt,
                profile=profile,
                working_dir=Path(workspace),
                event_callback=event_callback,
            )
        finally:
            if writer is not None:
                try:
                    writer.close()
                except Exception:
                    log.exception("stream_writer.close_failed", ticket=ctx.ticket_key)

        if ctx is not None:
            ctx.total_cost_usd += result.cost_usd
            ctx.cost_history.append(
                CostEntry(
                    cost_usd=result.cost_usd,
                    turns=result.turns_used,
                    profile=self._profile_name(),
                    state=self.state.value,
                )
            )
        return result

    def _profile_name(self) -> str:
        cfg = self.agent_config
        if cfg is None:
            return "unknown"
        if cfg is self._config.doc_checker:
            return "doc_checker"
        if cfg is self._config.standard:
            return "standard"
        if cfg is self._config.heavy:
            return "heavy"
        return "unknown"


class BaseApprovalState(BaseState):
    """Base class for approval-waiting states (lgtm/retry pattern).

    Uses the BoardProvider's check_approval contract to detect decisions.
    The stored comment_id is the tag string (e.g. `[ts:KEY:state:shortid]`)
    which survives state recovery better than native comment IDs.
    """

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    @abstractmethod
    def comment_meta_key(self) -> str:
        """Metadata key where the polled comment tag is stored."""
        ...

    @property
    @abstractmethod
    def trigger_on_approve(self) -> str: ...

    @property
    @abstractmethod
    def trigger_on_retry(self) -> str: ...

    @property
    @abstractmethod
    def ts_tag_state(self) -> str:
        """State name used in the tag (e.g. 'implementing' for mr_comment_id)."""
        ...

    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        comment_tag = ctx.get_meta(self.comment_meta_key)
        if not comment_tag:
            comment_tag = await self._recover_latest_tag(ticket, svc)
            if comment_tag:
                ctx.set_meta(self.comment_meta_key, comment_tag)
                log.info(
                    "Recovered tag from comments",
                    ticket=ticket.key,
                    tag=comment_tag,
                )
            else:
                log.warning(
                    "No tag found in comments",
                    ticket=ticket.key,
                    state=self.ts_tag_state,
                )
                return "_wait"

        result = await svc.board.check_approval(ticket.key, comment_tag)
        ctx.set_meta("reviewer_feedback", result.feedback or "")

        if result.feedback:
            log.info(
                "Reviewer feedback captured",
                ticket=ticket.key,
                feedback=result.feedback[:100],
            )

        match result.decision:
            case ApprovalDecision.APPROVED:
                ctx.retry_count = 0
                return self.trigger_on_approve
            case ApprovalDecision.RETRY:
                ack_tag = self._build_tag(ticket.key)
                posted = await svc.board.post_tagged_comment(
                    ticket.key,
                    ack_tag,
                    "On it... processing feedback.",
                )
                ctx.set_meta(self.comment_meta_key, posted)
                return self.trigger_on_retry
            case _:
                return "_wait"

    async def _recover_latest_tag(self, ticket: Ticket, svc: StateServices) -> str | None:
        """Scan comments for the most recent tag matching this ticket + state."""
        pattern = re.compile(
            rf"\[ts:{re.escape(ticket.key)}:{re.escape(self.ts_tag_state)}:[a-z0-9]+\]"
        )
        comments = await svc.board.list_comments(ticket.key)
        for comment in reversed(comments):
            match = pattern.search(comment.body)
            if match:
                return match.group(0)
        return None

    def _build_tag(self, ticket_key: str) -> str:
        """Create a fresh tag for this state."""
        short_id = uuid.uuid4().hex[:8]
        return f"[ts:{ticket_key}:{self.ts_tag_state}:{short_id}]"
