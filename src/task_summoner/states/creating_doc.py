"""CREATING_DOC → runs /create-design skill to generate architecture doc."""

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

    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> tuple[str, str]:
        system_prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
        )

        user_prompt = (
            f'Use the Skill tool: Skill(skill="aiops-workflows:create-design", '
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
            agent_name="doc_creator",
        )

        ctx.total_cost_usd += result.cost_usd

        if result.success:
            log.info("Design doc created", ticket=ticket.key)
            return "doc_created"

        ctx.error = result.error or "Failed to create design doc"
        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            return "doc_failed"
        log.warning("Doc creation failed, will retry", ticket=ticket.key, attempt=ctx.retry_count)
        return "_retry"
