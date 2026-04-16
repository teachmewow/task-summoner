"""PLANNING → runs the ticket-plan skill and posts the plan for review."""

from __future__ import annotations

import structlog

from task_summoner.config import AgentConfig
from task_summoner.constants import APPROVAL_INSTRUCTIONS
from task_summoner.models import Ticket, TicketContext, TicketState

from .base import BaseState, StateServices

log = structlog.get_logger()


class PlanningState(BaseState):

    @property
    def state(self) -> TicketState:
        return TicketState.PLANNING

    @property
    def requires_agent(self) -> bool:
        return True

    @property
    def agent_config(self) -> AgentConfig:
        return self._config.standard

    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> str:
        artifact_dir = self._artifact_dir(ticket.key)
        prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
            f"Save the plan to: {artifact_dir}/plan.md\n\n"
            f'Use the Skill tool: Skill(skill="tmw-workflows:ticket-plan", '
            f'args="{ticket.key} --headless")\n'
        )
        feedback = ctx.get_meta("reviewer_feedback", "")
        if feedback:
            prompt += f"\nReviewer feedback: {feedback}\n"
        return prompt

    async def handle(
        self, ctx: TicketContext, ticket: Ticket, svc: StateServices
    ) -> str:
        workspace = await self._ensure_workspace(ctx, ticket, svc)
        prompt = self.build_prompt(ctx, ticket)

        result = await self._run_agent(svc, "planner", prompt, workspace)

        artifact_dir = self._artifact_dir(ticket.key)
        plan_path = artifact_dir / "plan.md"

        ctx.total_cost_usd += result.cost_usd

        if plan_path.exists():
            plan_text = plan_path.read_text()
            tag = _build_tag(ticket.key, "planning")
            body = f"{plan_text}\n\n{APPROVAL_INSTRUCTIONS}"
            posted = await svc.board.post_tagged_comment(ticket.key, tag, body)
            ctx.set_meta("plan_comment_id", posted)
            return "plan_complete"

        ctx.error = result.error or "Planner did not produce a plan"
        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            return "plan_failed"
        log.warning(
            "Planning failed, will retry",
            ticket=ticket.key,
            attempt=ctx.retry_count,
        )
        return "_retry"


def _build_tag(ticket_key: str, state: str) -> str:
    import uuid

    return f"[ts:{ticket_key}:{state}:{uuid.uuid4().hex[:8]}]"
