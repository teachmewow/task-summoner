"""IMPLEMENTING → runs the ticket-implement skill, creates PR."""

from __future__ import annotations

import re
import uuid

import structlog

from task_summoner.config import AgentConfig
from task_summoner.constants import APPROVAL_INSTRUCTIONS
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.observability import state_trace_metadata, traceable

from .base import GATE_SUMMARY_FALLBACK, BaseState, StateServices, _extract_gate_summary

log = structlog.get_logger()

_PR_URL_PATTERN = re.compile(
    r"(https?://(?:gitlab[^\s)\"']+/-/merge_requests|github\.com/[^\s)\"']+/pull)/\d+)"
)


class ImplementingState(BaseState):
    @property
    def state(self) -> TicketState:
        return TicketState.IMPLEMENTING

    @property
    def requires_agent(self) -> bool:
        return True

    @property
    def agent_config(self) -> AgentConfig:
        return self._config.heavy

    @traceable(run_type="prompt", name="prompt.implementing")
    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> str:
        artifact_dir = self._artifact_dir(ticket.key)
        prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
            f"Save implementation report to: {artifact_dir}/implementation_report.md\n\n"
            f'Use the Skill tool: Skill(skill="task-summoner-workflows:ticket-implement", '
            f'args="{ticket.key} --headless")\n'
        )
        feedback = ctx.get_meta("reviewer_feedback", "")
        if feedback:
            prompt += f"\nReviewer feedback: {feedback}\n"
        return prompt

    @traceable(
        run_type="chain",
        name="state.implementing",
        metadata_fn=state_trace_metadata,
    )
    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        prompt = self.build_prompt(ctx, ticket)

        result = await self._run_agent(svc, "implementer", prompt, workspace, ctx=ctx)

        report_path = self._artifact_dir(ticket.key) / "implementation_report.md"
        report_text = report_path.read_text() if report_path.exists() else ""
        for source in (result.output, report_text):
            match = _PR_URL_PATTERN.search(source)
            if match:
                ctx.mr_url = match.group(1)
                break

        if result.success and ctx.mr_url:
            tag = _build_tag(ticket.key, "implementing")
            summary = _resolve_summary(_combine_sources(result.output, report_text), ticket.key)
            ctx.set_meta("gate_summary", summary)
            body = _compose_impl_body(ctx.mr_url, summary)
            posted = await svc.board.post_tagged_comment(ticket.key, tag, body)
            ctx.set_meta("mr_comment_id", posted)
            return "mr_created"

        ctx.error = result.error or "Implementation did not produce a PR"
        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            return "impl_failed"
        log.warning(
            "Implementation failed, will retry",
            ticket=ticket.key,
            attempt=ctx.retry_count,
        )
        return "_retry"


def _build_tag(ticket_key: str, state: str) -> str:
    return f"[ts:{ticket_key}:{state}:{uuid.uuid4().hex[:8]}]"


def _combine_sources(*parts: str | None) -> str:
    """Join agent output + persisted report so either can carry GATE_SUMMARY."""
    return "\n".join(p for p in parts if p)


def _resolve_summary(output: str, ticket_key: str) -> str:
    """Return the skill's GATE_SUMMARY sentence or the fallback, logging misses."""
    summary = _extract_gate_summary(output)
    if summary is None:
        log.warning(
            "GATE_SUMMARY missing from agent output",
            ticket=ticket_key,
            state=TicketState.IMPLEMENTING.value,
        )
        return GATE_SUMMARY_FALLBACK
    return summary


def _compose_impl_body(mr_url: str, summary: str) -> str:
    """Code-review body: PR link, one-line summary, approval CTA."""
    return f"PR created: [{mr_url}]({mr_url})\n\n{summary}\n\n{APPROVAL_INSTRUCTIONS}"
