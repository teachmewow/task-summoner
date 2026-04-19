"""CHECKING_DOC → agent checks if a design doc exists and if one is needed."""

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

_CONFLUENCE_URL_PATTERN = re.compile(r"(https?://[^\s)\"']*atlassian[^\s)\"']*wiki[^\s)\"']*)")


class CheckingDocState(BaseState):
    @property
    def state(self) -> TicketState:
        return TicketState.CHECKING_DOC

    @property
    def requires_agent(self) -> bool:
        return True

    @property
    def agent_config(self) -> AgentConfig:
        return self._config.doc_checker

    @traceable(run_type="prompt", name="prompt.checking_doc")
    def build_prompt(self, ticket: Ticket) -> str:
        return (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
            "Your final line MUST be one of: DOC_EXISTS <url>, DOC_NEEDED, DOC_NOT_NEEDED\n\n"
            f'Use the Skill tool: Skill(skill="task-summoner-workflows:ticket-plan", '
            f'args="{ticket.key} --headless")\n'
        )

    @traceable(
        run_type="chain",
        name="state.checking_doc",
        metadata_fn=state_trace_metadata,
    )
    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        prompt = self.build_prompt(ticket)

        result = await self._run_agent(svc, "doc_checker", prompt, workspace, ctx=ctx)
        output = result.output.strip()
        output_upper = output.upper()
        summary = _resolve_summary(output, ticket.key, self.state.value)
        ctx.set_meta("gate_summary", summary)

        tag = self._build_tag(ticket.key, "checking_doc")

        if "DOC_EXISTS" in output_upper:
            url_match = _CONFLUENCE_URL_PATTERN.search(output)
            url = url_match.group(1) if url_match else "URL not found"
            ctx.set_meta("confluence_page_url", url)

            body = _compose_body(f"Design doc found: [{url}]({url})", summary)
            posted = await svc.board.post_tagged_comment(ticket.key, tag, body)
            ctx.set_meta("doc_comment_id", posted)

            log.info("Design doc found", ticket=ticket.key, url=url)
            return "doc_exists"

        if "DOC_NOT_NEEDED" in output_upper:
            body = _compose_body("Design doc not required.", summary)
            posted = await svc.board.post_tagged_comment(ticket.key, tag, body)
            ctx.set_meta("doc_comment_id", posted)

            log.info("Design doc not needed", ticket=ticket.key)
            return "doc_not_needed"

        body = _compose_body("Design doc required, creating now.", summary)
        posted = await svc.board.post_tagged_comment(ticket.key, tag, body)
        ctx.set_meta("doc_comment_id", posted)

        log.info("Design doc needed", ticket=ticket.key)
        return "doc_needed"

    def _build_tag(self, ticket_key: str, state: str) -> str:
        return f"[ts:{ticket_key}:{state}:{uuid.uuid4().hex[:8]}]"


def _resolve_summary(output: str, ticket_key: str, state: str) -> str:
    """Return the skill's GATE_SUMMARY sentence or the fallback, logging misses.

    A missing ``GATE_SUMMARY`` is usually a skill bug (the Final line contract
    was skipped). We degrade gracefully — the gate still fires — but surface
    the miss so it can be tracked down.
    """
    summary = _extract_gate_summary(output)
    if summary is None:
        log.warning(
            "GATE_SUMMARY missing from agent output",
            ticket=ticket_key,
            state=state,
        )
        return GATE_SUMMARY_FALLBACK
    return summary


def _compose_body(verdict: str, summary: str) -> str:
    """Assemble the Linear comment body for a pre-gate approval prompt.

    Shape (≤ 5 short lines):

        <verdict header>

        <GATE_SUMMARY (or fallback)>

        <APPROVAL_INSTRUCTIONS>

    The raw agent narrative is intentionally dropped — it lives in
    ``stream.jsonl`` / the Activity Timeline for debugging.
    """
    return "\n\n".join((verdict, summary, APPROVAL_INSTRUCTIONS))
