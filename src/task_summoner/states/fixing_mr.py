"""FIXING_MR → reads open MR threads, self-critiques, and fixes issues."""

from __future__ import annotations

import structlog

from task_summoner.config import AgentConfig
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.tracker import Adf, MessageTag

from .base import BaseState, StateServices

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

    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> tuple[str, str]:
        system_prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
        )

        user_prompt = (
            f'Use the Skill tool: Skill(skill="aiops-workflows:address-mr-feedback", '
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
            agent_name="mr_fixer",
        )

        ctx.total_cost_usd += result.cost_usd

        if result.success:
            tag = MessageTag(ticket_key=ticket.key, state="fixing_mr")
            comment = tag.embed_in_adf(
                Adf.paragraph("Review feedback addressed. Please re-review."),
                Adf.paragraph('Reply with "lgtm" to approve, or "retry" if more changes needed.'),
            )
            await svc.jira.post_comment(ticket.key, comment)
            ctx.set_meta("mr_comment_id", tag.tag)
            return "fixed"

        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            ctx.error = result.error or "Failed to fix MR"
            return "fix_failed"
        return "_retry"
