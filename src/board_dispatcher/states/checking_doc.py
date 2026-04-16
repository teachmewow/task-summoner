"""CHECKING_DOC → agent checks if a design doc exists and if one is needed.

Posts a Jira comment with bd tag for robust identification,
then transitions to WAITING_DOC_REVIEW for human approval.
"""

from __future__ import annotations

import re

import structlog

from board_dispatcher.config import AgentConfig
from board_dispatcher.models import Ticket, TicketContext, TicketState
from board_dispatcher.constants import APPROVAL_INSTRUCTIONS
from board_dispatcher.tracker import Adf, MessageTag

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

    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> tuple[str, str]:
        system_prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
            "Your final line MUST be one of: DOC_EXISTS <url>, DOC_NEEDED, DOC_NOT_NEEDED\n"
        )

        user_prompt = (
            f'Use the Skill tool: Skill(skill="aiops-workflows:check-design-doc", '
            f'args="{ticket.key} --headless")\n'
        )

        return system_prompt, user_prompt

    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        system_prompt, user_prompt = self.build_prompt(ctx, ticket)

        result = await svc.agent_runner.run(
            prompt=user_prompt,
            system_prompt=system_prompt,
            cwd=workspace,
            agent_config=self.agent_config,
            ticket_key=ticket.key,
            agent_name="doc_checker",
        )

        ctx.total_cost_usd += result.cost_usd
        output = result.output.strip()
        output_upper = output.upper()
        reasoning = _extract_reasoning(output)

        # Create the bd tag for this comment
        tag = MessageTag(ticket_key=ticket.key, state="checking_doc")

        if "DOC_EXISTS" in output_upper:
            url_match = _CONFLUENCE_URL_PATTERN.search(output)
            url = url_match.group(1) if url_match else "URL not found"
            ctx.set_meta("confluence_page_url", url)

            paras = [Adf.paragraph("Design doc found: ", Adf.link(url, url))]
            if reasoning:
                paras.append(Adf.paragraph(reasoning))
            paras.append(Adf.paragraph("Next step: proceed to Planning phase."))
            paras.append(Adf.paragraph(APPROVAL_INSTRUCTIONS))
            comment = tag.embed_in_adf(*paras)
            await svc.jira.post_comment(ticket.key, comment)
            ctx.set_meta("doc_comment_id", tag.tag)

            log.info("Design doc found", ticket=ticket.key, url=url)
            return "doc_exists"

        elif "DOC_NOT_NEEDED" in output_upper:
            paras = [Adf.paragraph("Design doc not required.")]
            if reasoning:
                paras.append(Adf.paragraph(reasoning))
            paras.append(Adf.paragraph("Next step: skip doc creation and proceed to Planning phase."))
            paras.append(Adf.paragraph(APPROVAL_INSTRUCTIONS))
            comment = tag.embed_in_adf(*paras)
            await svc.jira.post_comment(ticket.key, comment)
            ctx.set_meta("doc_comment_id", tag.tag)

            log.info("Design doc not needed", ticket=ticket.key)
            return "doc_not_needed"

        else:
            log.info("Design doc needed", ticket=ticket.key)
            return "doc_needed"


def _extract_reasoning(output: str) -> str:
    """Extract the agent's reasoning from output (everything before the verdict line)."""
    lines = output.strip().splitlines()
    reasoning_lines = []
    for line in lines:
        upper = line.strip().upper()
        if upper.startswith(("DOC_EXISTS", "DOC_NOT_NEEDED", "DOC_NEEDED")):
            break
        if line.strip():
            reasoning_lines.append(line.strip())
    return " ".join(reasoning_lines)
