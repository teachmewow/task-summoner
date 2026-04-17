"""CHECKING_DOC → agent checks if a design doc exists and if one is needed."""

from __future__ import annotations

import re
import uuid

import structlog

from task_summoner.config import AgentConfig
from task_summoner.constants import APPROVAL_INSTRUCTIONS
from task_summoner.models import Ticket, TicketContext, TicketState

from .base import BaseState, StateServices

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

    def build_prompt(self, ticket: Ticket) -> str:
        return (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
            "Your final line MUST be one of: DOC_EXISTS <url>, DOC_NEEDED, DOC_NOT_NEEDED\n\n"
            f'Use the Skill tool: Skill(skill="tmw-workflows:ticket-plan", '
            f'args="{ticket.key} --headless")\n'
        )

    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        prompt = self.build_prompt(ticket)

        result = await self._run_agent(svc, "doc_checker", prompt, workspace, ctx=ctx)
        output = result.output.strip()
        output_upper = output.upper()
        reasoning = _extract_reasoning(output)

        tag = self._build_tag(ticket.key, "checking_doc")

        if "DOC_EXISTS" in output_upper:
            url_match = _CONFLUENCE_URL_PATTERN.search(output)
            url = url_match.group(1) if url_match else "URL not found"
            ctx.set_meta("confluence_page_url", url)

            body = _compose_body(
                f"Design doc found: [{url}]({url})",
                reasoning,
                "Next step: proceed to Planning phase.",
                APPROVAL_INSTRUCTIONS,
            )
            posted = await svc.board.post_tagged_comment(ticket.key, tag, body)
            ctx.set_meta("doc_comment_id", posted)

            log.info("Design doc found", ticket=ticket.key, url=url)
            return "doc_exists"

        if "DOC_NOT_NEEDED" in output_upper:
            body = _compose_body(
                "Design doc not required.",
                reasoning,
                "Next step: skip doc creation and proceed to Planning phase.",
                APPROVAL_INSTRUCTIONS,
            )
            posted = await svc.board.post_tagged_comment(ticket.key, tag, body)
            ctx.set_meta("doc_comment_id", posted)

            log.info("Design doc not needed", ticket=ticket.key)
            return "doc_not_needed"

        log.info("Design doc needed", ticket=ticket.key)
        return "doc_needed"

    def _build_tag(self, ticket_key: str, state: str) -> str:
        return f"[ts:{ticket_key}:{state}:{uuid.uuid4().hex[:8]}]"


def _extract_reasoning(output: str) -> str:
    lines = output.strip().splitlines()
    reasoning_lines = []
    for line in lines:
        upper = line.strip().upper()
        if upper.startswith(("DOC_EXISTS", "DOC_NOT_NEEDED", "DOC_NEEDED")):
            break
        if line.strip():
            reasoning_lines.append(line.strip())
    return " ".join(reasoning_lines)


def _compose_body(*parts: str) -> str:
    return "\n\n".join(p for p in parts if p)
