"""PLANNING → runs /ticket-plan skill to generate implementation plan.

The orchestrator posts the plan to Jira with a bd tag, not the agent.
"""

from __future__ import annotations

import structlog

from task_summoner.config import AgentConfig
from task_summoner.constants import APPROVAL_INSTRUCTIONS
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.tracker import Adf, MessageTag
from task_summoner.tracker.adf_converter import markdown_to_adf

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

    def build_prompt(self, ctx: TicketContext, ticket: Ticket) -> tuple[str, str]:
        artifact_dir = self._artifact_dir(ticket.key)

        system_prompt = (
            "You are a headless agent. Invoke the skill and follow its instructions.\n"
            f"Save the plan to: {artifact_dir}/plan.md\n"
        )

        user_prompt = (
            f'Use the Skill tool: Skill(skill="aiops-workflows:ticket-plan", '
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
            agent_name="planner",
        )

        artifact_dir = self._artifact_dir(ticket.key)
        plan_path = artifact_dir / "plan.md"

        ctx.total_cost_usd += result.cost_usd

        if plan_path.exists():
            plan_text = plan_path.read_text()
            plan_nodes = markdown_to_adf(plan_text)
            tag = MessageTag(ticket_key=ticket.key, state="planning")
            comment = tag.embed_nodes_in_adf(plan_nodes, Adf.paragraph(APPROVAL_INSTRUCTIONS))
            await svc.jira.post_comment(ticket.key, comment)
            ctx.set_meta("plan_comment_id", tag.tag)
            return "plan_complete"

        ctx.error = result.error or "Planner did not produce a plan"
        ctx.retry_count += 1
        if ctx.retry_count >= self._config.retry.max_retries:
            return "plan_failed"
        log.warning("Planning failed, will retry", ticket=ticket.key, attempt=ctx.retry_count)
        return "_retry"
