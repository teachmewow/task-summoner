"""BoardProvider protocol — the contract all board providers must implement."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from task_summoner.models.enums import TicketState
from task_summoner.models.ticket import Ticket
from task_summoner.models.comment import Comment


@runtime_checkable
class BoardProvider(Protocol):
    """Abstract interface for board providers (Jira, Linear, etc.)."""

    async def search_eligible(self) -> list[Ticket]:
        """Find tickets eligible for processing (matching watch label, not terminal)."""
        ...

    async def fetch_ticket(self, ticket_id: str) -> Ticket:
        """Fetch full ticket details by ID."""
        ...

    async def post_comment(self, ticket_id: str, body: str) -> str:
        """Post a Markdown comment on a ticket. Returns the comment ID."""
        ...

    async def list_comments(self, ticket_id: str) -> list[Comment]:
        """List all comments on a ticket."""
        ...

    async def transition(self, ticket_id: str, status: str) -> None:
        """Transition a ticket to a new status."""
        ...

    async def add_label(self, ticket_id: str, label: str) -> None:
        """Add a label to a ticket."""
        ...

    async def remove_label(self, ticket_id: str, label: str) -> None:
        """Remove a label from a ticket."""
        ...

    async def assign(self, ticket_id: str, assignee: str | None) -> None:
        """Assign a ticket to a user, or unassign if None."""
        ...

    async def set_state_label(self, ticket_id: str, state: TicketState) -> None:
        """Set a ts:<state> label on the ticket, removing previous state labels."""
        ...

    async def get_comment_replies(
        self, ticket_id: str, after_comment_id: str
    ) -> list[Comment]:
        """Get comments posted after a specific comment (for approval polling)."""
        ...
