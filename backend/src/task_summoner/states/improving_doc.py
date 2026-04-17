"""IMPROVING_DOC → reads inline comments and improves the design doc."""

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

    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> str:
        page_id = ctx.get_meta("confluence_page_id", "")
        prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n\n"
            f'Use the Skill tool: Skill(skill="tmw-workflows:improve-design-doc", '
            f'args="{page_id} --headless")\n'
        )
        feedback = ctx.get_meta("reviewer_feedback", "")
        if feedback:
            prompt += f"\nReviewer feedback: {feedback}\n"
        return prompt

    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        prompt = self.build_prompt(ctx, ticket)

        result = await self._run_agent(svc, "doc_improver", prompt, workspace)
        ctx.total_cost_usd += result.cost_usd

        if result.success:
            return "improved"

        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            ctx.error = result.error or "Failed to improve doc"
            return "improve_failed"
        return "_retry"
