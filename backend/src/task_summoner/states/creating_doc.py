"""CREATING_DOC → runs the design-doc skill.

Post-invocation verification is mandatory: the agent returns ``success=True``
whenever the SDK stream closed cleanly, but an SDK-clean run does not imply
an RFC artefact landed on the docs repo. The handler checks for the
``rfc/<issue-key-lower>`` branch on the configured docs repo (remote or local
worktree) before advancing the FSM. Without this check a mis-typed skill name
or a skill that short-circuits on its classifier-verdict gate produces zero
output while still spending budget — the silent failure mode this state was
rewritten to eliminate.
"""

from __future__ import annotations

import re

import structlog

from task_summoner.config import AgentConfig
from task_summoner.docs_repo import DocsRepoError, require_docs_repo
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.observability import state_trace_metadata, traceable
from task_summoner.utils import run_cli

from .base import BaseState, StateServices

log = structlog.get_logger()

# Skills emit this line in their final summary. We grep for it in the agent
# output so the Linear comment and ctx.metadata can surface the real PR URL.
_PR_URL_PATTERN = re.compile(r"(https?://github\.com/[^\s)\"']+/pull/\d+)")

# Trimmed agent-output budget for structured logging. The full output goes to
# the event bus; this is just for log readability.
_OUTPUT_LOG_CHARS = 800


class CreatingDocState(BaseState):
    @property
    def state(self) -> TicketState:
        return TicketState.CREATING_DOC

    @property
    def requires_agent(self) -> bool:
        return True

    @property
    def agent_config(self) -> AgentConfig:
        return self._config.standard

    @traceable(run_type="prompt", name="prompt.creating_doc")
    def build_prompt(self, ticket: Ticket) -> str:
        return (
            "You are a headless agent. Invoke the skill and follow its instructions.\n\n"
            f'Use the Skill tool: Skill(skill="task-summoner-workflows:create-design-doc", '
            f'args="{ticket.key} --headless")\n'
        )

    @traceable(
        run_type="chain",
        name="state.creating_doc",
        metadata_fn=state_trace_metadata,
    )
    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        prompt = self.build_prompt(ticket)
        log.info(
            "Creating design doc",
            ticket=ticket.key,
            workspace=workspace,
            prompt_chars=len(prompt),
        )

        result = await self._run_agent(svc, "doc_creator", prompt, workspace, ctx=ctx)

        output_tail = (result.output or "")[-_OUTPUT_LOG_CHARS:]
        log.info(
            "Doc creator agent finished",
            ticket=ticket.key,
            success=result.success,
            turns=result.turns_used,
            cost_usd=round(result.cost_usd, 4),
            output_tail=output_tail,
        )

        if not result.success:
            return await self._fail(
                ctx,
                ticket,
                svc,
                result.error or "Failed to create design doc",
            )

        branch = _rfc_branch_for(ticket.key)
        verification = await _verify_rfc_branch(branch)
        log.info(
            "RFC artifact verification",
            ticket=ticket.key,
            branch=branch,
            branch_present=verification.branch_present,
            method=verification.method,
            detail=verification.detail,
        )

        if not verification.branch_present:
            reason = (
                f"Agent finished but no RFC artifact was created on branch `{branch}`.\n"
                f"Verification: {verification.detail}.\n"
                f"Inspect stream log for agent-output-tail:\n\n```\n{output_tail}\n```"
            )
            return await self._fail(ctx, ticket, svc, reason)

        pr_url_match = _PR_URL_PATTERN.search(result.output or "")
        if pr_url_match:
            ctx.set_meta("rfc_pr_url", pr_url_match.group(1))
        ctx.set_meta("rfc_branch", branch)
        ctx.retry_count = 0
        ctx.error = None
        log.info(
            "Design doc created",
            ticket=ticket.key,
            branch=branch,
            pr_url=ctx.get_meta("rfc_pr_url"),
        )
        return "doc_created"

    async def _fail(
        self,
        ctx: TicketContext,
        ticket: Ticket,
        svc: StateServices,
        reason: str,
    ) -> str:
        """Record the failure, notify the board, and return the retry / fail trigger.

        The Linear comment is best-effort — a comment-post failure must not
        mask the underlying RFC failure, so we log-and-continue rather than
        re-raise.
        """
        ctx.error = reason
        ctx.retry_count += 1
        log.warning(
            "Doc creation failed",
            ticket=ticket.key,
            attempt=ctx.retry_count,
            reason=reason[:240],
        )
        try:
            await svc.board.post_comment(
                ticket.key,
                f"Automated doc creation failed (attempt {ctx.retry_count}).\n\n{reason}",
            )
        except Exception as post_err:  # noqa: BLE001 — best-effort notification
            log.warning(
                "Failed to post failure comment",
                ticket=ticket.key,
                error=str(post_err),
            )
        if ctx.retry_count >= self._config.retry.max_retries:
            return "doc_failed"
        return "_retry"


def _rfc_branch_for(ticket_key: str) -> str:
    """Mirror ``create-design-doc``'s branch convention: ``rfc/<issue-id-lower>``."""
    return f"rfc/{ticket_key.lower()}"


class _BranchCheck:
    """Lightweight result object for RFC branch verification.

    Not a dataclass so it stays trivial to mock in tests.
    """

    __slots__ = ("branch_present", "method", "detail")

    def __init__(self, *, branch_present: bool, method: str, detail: str) -> None:
        self.branch_present = branch_present
        self.method = method
        self.detail = detail


async def _verify_rfc_branch(branch: str) -> _BranchCheck:
    """Ask the configured docs repo whether ``branch`` exists.

    Preference order:

    1. ``git ls-remote --heads origin <branch>`` from the docs repo working
       copy — authoritative, catches the "PR was pushed" case.
    2. ``git show-ref --verify refs/heads/<branch>`` — fallback for offline
       runs where the branch is only local so far.

    Any failure to resolve / reach the docs repo is treated as "branch
    missing" so the state transitions to FAILED rather than silently
    pretending the artifact exists.
    """
    try:
        docs_repo = require_docs_repo()
    except DocsRepoError as e:
        return _BranchCheck(
            branch_present=False,
            method="docs_repo",
            detail=f"docs_repo unavailable: {e}",
        )

    try:
        stdout = await run_cli(
            ["git", "-C", str(docs_repo), "ls-remote", "--heads", "origin", branch],
            timeout_sec=15,
        )
    except RuntimeError as e:
        stdout = ""
        remote_error = str(e)
    else:
        remote_error = ""

    if stdout.strip():
        return _BranchCheck(
            branch_present=True,
            method="ls-remote",
            detail=f"{branch} present on origin",
        )

    try:
        await run_cli(
            ["git", "-C", str(docs_repo), "show-ref", "--verify", f"refs/heads/{branch}"],
            timeout_sec=5,
        )
    except RuntimeError:
        local_present = False
    else:
        local_present = True

    if local_present:
        return _BranchCheck(
            branch_present=True,
            method="show-ref",
            detail=f"{branch} present locally (not yet pushed)",
        )

    detail_parts = [f"{branch} not found on origin or locally"]
    if remote_error:
        detail_parts.append(f"ls-remote error: {remote_error}")
    return _BranchCheck(
        branch_present=False,
        method="ls-remote+show-ref",
        detail="; ".join(detail_parts),
    )
