"""IMPROVING_DOC → reads inline comments and improves the design doc."""

from __future__ import annotations

import structlog

from task_summoner.config import AgentConfig
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.observability import state_trace_metadata, traceable

from .base import (
    GATE_SUMMARY_ECHO_INSTRUCTION,
    BaseState,
    StateServices,
    _extract_gate_summary,
)

log = structlog.get_logger()


class ImprovingDocState(BaseState):
    @property
    def state(self) -> TicketState:
        return TicketState.IMPROVING_DOC

    @property
    def requires_agent(self) -> bool:
        return True

    @property
    def agent_config(self) -> AgentConfig:
        return self._config.standard

    @traceable(run_type="prompt", name="prompt.improving_doc")
    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> str:
        # address-doc-feedback reads open PR review comments itself. The human
        # can click "retry" with no text (skill just reads the PR) or add an
        # optional UI note that is forwarded as a "user said" preamble.
        prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n\n"
            f'Use the Skill tool: Skill(skill="task-summoner-workflows:address-doc-feedback", '
            f'args="{ticket.key} --headless")\n\n'
            f"{GATE_SUMMARY_ECHO_INSTRUCTION}\n"
        )
        feedback = ctx.get_meta("reviewer_feedback", "")
        if feedback:
            prompt += f'\nUsuário disse: "{feedback}"\n'
        return prompt

    @traceable(
        run_type="chain",
        name="state.improving_doc",
        metadata_fn=state_trace_metadata,
    )
    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        prompt = self.build_prompt(ctx, ticket)

        result = await self._run_agent(svc, "doc_improver", prompt, workspace, ctx=ctx)

        if result.success:
            ctx.set_meta("gate_summary", _resolve_summary(result.output or "", ticket.key))
            return "improved"

        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            ctx.error = result.error or "Failed to improve doc"
            return "improve_failed"
        return "_retry"


def _resolve_summary(output: str, ticket_key: str) -> str:
    """Return the skill's GATE_SUMMARY sentence, with a contextual fallback."""
    summary = _extract_gate_summary(output)
    if summary is not None:
        return summary
    log.warning(
        "GATE_SUMMARY missing from agent output",
        ticket=ticket_key,
        state=TicketState.IMPROVING_DOC.value,
    )
    return f"Design doc revised for {ticket_key}; re-review PR."
