"""Terminal states — DONE and FAILED."""

from __future__ import annotations

import structlog

from task_summoner.models import Ticket, TicketContext, TicketState

from .base import BaseState, StateServices

log = structlog.get_logger()


class DoneState(BaseState):

    @property
    def state(self) -> TicketState:
        return TicketState.DONE

    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        await svc.jira.transition(ticket.key, "Done")
        log.info("Ticket done", ticket=ticket.key, cost=f"${ctx.total_cost_usd:.2f}")
        return "_noop"


class FailedState(BaseState):

    @property
    def state(self) -> TicketState:
        return TicketState.FAILED

    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        return "_noop"
