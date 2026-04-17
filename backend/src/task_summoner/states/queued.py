"""QUEUED → create workspace, claim ticket, move to CHECKING_DOC."""

from __future__ import annotations

import structlog

from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.workspace import derive_branch_name

from .base import BaseState, StateServices

log = structlog.get_logger()


class QueuedState(BaseState):
    @property
    def state(self) -> TicketState:
        return TicketState.QUEUED

    async def handle(self, ctx: TicketContext, ticket: Ticket, svc: StateServices) -> str:
        repo_name, repo_path = self._config.resolve_repo(ticket.labels)
        branch = derive_branch_name(ticket)

        workspace = await svc.workspace.create(ticket.key, branch, repo_path)
        ctx.branch_name = branch
        ctx.workspace_path = workspace

        await svc.board.assign(ticket.key, "@me")
        await svc.board.transition(ticket.key, "In Progress")
        await svc.board.add_label(ticket.key, f"branch:{branch}")

        log.info("Ticket claimed", ticket=ticket.key, branch=branch, repo=repo_name)
        return "start"
