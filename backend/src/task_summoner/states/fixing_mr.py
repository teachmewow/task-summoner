"""FIXING_MR → reads open PR threads, self-critiques, and fixes issues."""

from __future__ import annotations

import uuid

import structlog

from task_summoner.config import AgentConfig
from task_summoner.constants import APPROVAL_INSTRUCTIONS
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.observability import state_trace_metadata, traceable

from .base import GATE_SUMMARY_FALLBACK, BaseState, StateServices, _extract_gate_summary

log = structlog.get_logger()


class FixingMrState(BaseState):
    @property
    def state(self) -> TicketState:
        return TicketState.FIXING_MR

    @property
    def requires_agent(self) -> bool:
        return True

    @property
    def agent_config(self) -> AgentConfig:
        return self._config.standard

    @traceable(run_type="prompt", name="prompt.fixing_mr")
    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> str:
        prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n\n"
            f'Use the Skill tool: Skill(skill="task-summoner-workflows:review-pr", '
            f'args="{ticket.key} --headless")\n'
        )
        feedback = ctx.get_meta("reviewer_feedback", "")
        if feedback:
            prompt += f"\nReviewer feedback: {feedback}\n"
        return prompt

    @traceable(
        run_type="chain",
        name="state.fixing_mr",
        metadata_fn=state_trace_metadata,
    )
    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        prompt = self.build_prompt(ctx, ticket)

        result = await self._run_agent(svc, "mr_fixer", prompt, workspace, ctx=ctx)

        if result.success:
            tag = _build_tag(ticket.key, "fixing_mr")
            summary = _resolve_summary(result.output or "", ticket.key)
            ctx.set_meta("gate_summary", summary)
            body = _compose_fix_body(summary)
            posted = await svc.board.post_tagged_comment(ticket.key, tag, body)
            ctx.set_meta("mr_comment_id", posted)
            return "fixed"

        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            ctx.error = result.error or "Failed to fix PR"
            return "fix_failed"
        return "_retry"


def _build_tag(ticket_key: str, state: str) -> str:
    return f"[ts:{ticket_key}:{state}:{uuid.uuid4().hex[:8]}]"


def _resolve_summary(output: str, ticket_key: str) -> str:
    """Return the skill's GATE_SUMMARY sentence or the fallback, logging misses."""
    summary = _extract_gate_summary(output)
    if summary is None:
        log.warning(
            "GATE_SUMMARY missing from agent output",
            ticket=ticket_key,
            state=TicketState.FIXING_MR.value,
        )
        return GATE_SUMMARY_FALLBACK
    return summary


def _compose_fix_body(summary: str) -> str:
    """Re-review body: header + one-line summary + approval CTA."""
    return f"Review feedback addressed. Please re-review.\n\n{summary}\n\n{APPROVAL_INSTRUCTIONS}"
