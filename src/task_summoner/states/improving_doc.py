"""IMPROVING_DOC → reads inline Confluence comments and improves the design doc."""

from __future__ import annotations

import structlog

from task_summoner.config import AgentConfig
from task_summoner.models import Ticket, TicketContext, TicketState

from .base import BaseState, StateServices

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

    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> tuple[str, str]:
        page_id = ctx.get_meta("confluence_page_id", "")

        system_prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
        )

        user_prompt = (
            f'Use the Skill tool: Skill(skill="aiops-workflows:improve-design-doc", '
            f'args="{page_id} --headless")\n'
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
            agent_name="doc_improver",
        )

        ctx.total_cost_usd += result.cost_usd

        if result.success:
            return "improved"

        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            ctx.error = result.error or "Failed to improve doc"
            return "improve_failed"
        return "_retry"
