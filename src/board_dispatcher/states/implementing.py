"""IMPLEMENTING → runs /ticket-implement skill, creates MR."""

from __future__ import annotations

import re

import structlog

from board_dispatcher.config import AgentConfig
from board_dispatcher.models import Ticket, TicketContext, TicketState
from board_dispatcher.constants import APPROVAL_INSTRUCTIONS
from board_dispatcher.tracker import Adf, MessageTag

from .base import BaseState, StateServices

log = structlog.get_logger()

_MR_URL_PATTERN = re.compile(r"(https?://gitlab[^\s)\"']+/-?/merge_requests/\d+)")


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

    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> tuple[str, str]:
        artifact_dir = self._artifact_dir(ticket.key)
        system_prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
            f"Save implementation report to: {artifact_dir}/implementation_report.md\n"
        )

        user_prompt = (
            f'Use the Skill tool: Skill(skill="aiops-workflows:ticket-implement", '
            f'args="{ticket.key} --headless")\n'
        )

        feedback = ctx.get_meta("reviewer_feedback", "")
        if feedback:
            user_prompt += f"\nReviewer feedback: {feedback}\n"

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
            agent_name="implementer",
        )

        ctx.total_cost_usd += result.cost_usd

        # Extract MR URL
        report_path = self._artifact_dir(ticket.key) / "implementation_report.md"
        report_text = report_path.read_text() if report_path.exists() else ""
        for source in [result.output, report_text]:
            match = _MR_URL_PATTERN.search(source)
            if match:
                ctx.mr_url = match.group(1)
                break

        if result.success and ctx.mr_url:
            tag = MessageTag(ticket_key=ticket.key, state="implementing")
            comment = tag.embed_in_adf(
                Adf.paragraph("MR created: ", Adf.link(ctx.mr_url, ctx.mr_url)),
                Adf.paragraph(APPROVAL_INSTRUCTIONS),
            )
            await svc.jira.post_comment(ticket.key, comment)
            ctx.set_meta("mr_comment_id", tag.tag)
            return "mr_created"

        ctx.error = result.error or "Implementation did not produce an MR"
        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            return "impl_failed"
        log.warning("Implementation failed, will retry", ticket=ticket.key, attempt=ctx.retry_count)
        return "_retry"
