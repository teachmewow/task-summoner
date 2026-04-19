"""QUEUED → create workspace, claim ticket, route by label.

Doc vs no-doc routing is decided here, not by an LLM. The `Doc` label is
applied upstream by the `create-work-plan` skill (run by the human before
dispatch). Default is no doc — cheaper, faster, and the user can always
add the label to opt in.
"""

from __future__ import annotations

import structlog

from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.workspace import derive_branch_name

from .base import BaseState, StateServices

log = structlog.get_logger()

DOC_LABEL = "Doc"


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

        doc_required = DOC_LABEL in (ticket.labels or [])
        log.info(
            "Ticket claimed",
            ticket=ticket.key,
            branch=branch,
            repo=repo_name,
            doc_required=doc_required,
        )
        return "doc_required" if doc_required else "no_doc_needed"
