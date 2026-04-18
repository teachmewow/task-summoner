"""CREATING_DOC → runs the design-doc skill."""

from __future__ import annotations

import structlog

from task_summoner.config import AgentConfig
from task_summoner.models import Ticket, TicketContext, TicketState

from .base import BaseState, StateServices

log = structlog.get_logger()


class CreatingDocState(BaseState):
    @property
    def state(self) -> TicketState:
        return TicketState.CREATING_DOC

    @property
    def requires_agent(self) -> bool:
        return True

    @property
    def agent_config(self) -> AgentConfig:
        return self._config.standard

    def build_prompt(self, ticket: Ticket) -> str:
        return (
            "You are a headless agent. Invoke the skill and follow its instructions.\n\n"
            f'Use the Skill tool: Skill(skill="task-summoner-workflows:create-design", '
            f'args="{ticket.key} --headless")\n'
        )

    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        prompt = self.build_prompt(ticket)

        result = await self._run_agent(svc, "doc_creator", prompt, workspace, ctx=ctx)

        if result.success:
            log.info("Design doc created", ticket=ticket.key)
            return "doc_created"

        ctx.error = result.error or "Failed to create design doc"
        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            return "doc_failed"
        log.warning(
            "Doc creation failed, will retry",
            ticket=ticket.key,
            attempt=ctx.retry_count,
        )
        return "_retry"
