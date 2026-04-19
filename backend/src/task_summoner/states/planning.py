"""PLANNING → runs the ticket-plan skill and posts the plan for review."""

from __future__ import annotations

import re
import uuid

import structlog

from task_summoner.config import AgentConfig
from task_summoner.constants import APPROVAL_INSTRUCTIONS
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.observability import state_trace_metadata, traceable

from .base import (
    GATE_SUMMARY_ECHO_INSTRUCTION,
    BaseState,
    StateServices,
    _extract_gate_summary,
)

log = structlog.get_logger()

# The skill's Phase 5 opens a draft PR and echoes the URL. We grep for it so
# the gate endpoint can surface ``plan_pr_url`` to the UI — without it, gate
# inference has to re-discover the PR via ``gh``, which silently misses when
# the PR lives on a repo outside ``config.default_repo``.
_PR_URL_PATTERN = re.compile(r"(https?://github\.com/[^\s)\"']+/pull/\d+)")


class PlanningState(BaseState):
    @property
    def state(self) -> TicketState:
        return TicketState.PLANNING

    @property
    def requires_agent(self) -> bool:
        return True

    @property
    def agent_config(self) -> AgentConfig:
        return self._config.standard

    @traceable(run_type="prompt", name="prompt.planning")
    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> str:
        artifact_dir = self._artifact_dir(ticket.key)
        prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
            f"Save the plan to: {artifact_dir}/plan.md\n\n"
            f'Use the Skill tool: Skill(skill="task-summoner-workflows:ticket-plan", '
            f'args="{ticket.key} --headless")\n\n'
            f"{GATE_SUMMARY_ECHO_INSTRUCTION}\n"
        )
        feedback = ctx.get_meta("reviewer_feedback", "")
        if feedback:
            prompt += f'\nUsuário disse: "{feedback}"\n'
        return prompt

    @traceable(
        run_type="chain",
        name="state.planning",
        metadata_fn=state_trace_metadata,
    )
    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        prompt = self.build_prompt(ctx, ticket)

        result = await self._run_agent(svc, "planner", prompt, workspace, ctx=ctx)

        artifact_dir = self._artifact_dir(ticket.key)
        plan_path = artifact_dir / "plan.md"

        if plan_path.exists():
            plan_text = plan_path.read_text()
            tag = _build_tag(ticket.key, "planning")
            summary = _resolve_summary(result.output or "", ticket.key)
            ctx.set_meta("gate_summary", summary)
            pr_url_match = _PR_URL_PATTERN.search(result.output or "")
            if pr_url_match:
                ctx.set_meta("plan_pr_url", pr_url_match.group(1))
            body = _compose_plan_body(summary, plan_text)
            posted = await svc.board.post_tagged_comment(ticket.key, tag, body)
            ctx.set_meta("plan_comment_id", posted)
            return "plan_complete"

        ctx.error = result.error or "Planner did not produce a plan"
        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            return "plan_failed"
        log.warning(
            "Planning failed, will retry",
            ticket=ticket.key,
            attempt=ctx.retry_count,
        )
        return "_retry"


def _build_tag(ticket_key: str, state: str) -> str:
    return f"[ts:{ticket_key}:{state}:{uuid.uuid4().hex[:8]}]"


def _resolve_summary(output: str, ticket_key: str) -> str:
    """Return the skill's GATE_SUMMARY sentence, with a contextual fallback."""
    summary = _extract_gate_summary(output)
    if summary is not None:
        return summary
    log.warning(
        "GATE_SUMMARY missing from agent output",
        ticket=ticket_key,
        state=TicketState.PLANNING.value,
    )
    return f"Implementation plan drafted for {ticket_key}; plan.md ready for review."


def _compose_plan_body(summary: str, plan_text: str) -> str:
    """Plan-review body: one-line summary on top, full plan below, approval CTA."""
    return f"{summary}\n\n{plan_text}\n\n{APPROVAL_INSTRUCTIONS}"
