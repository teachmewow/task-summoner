"""Ticket response schema.

Direct re-export of the persisted `TicketContext` model — the API shape equals
the storage shape today. If those need to diverge later (e.g. hiding metadata,
renaming fields), introduce a distinct `TicketResponse(BaseModel)` here.
"""

from __future__ import annotations

from task_summoner.models import TicketContext

TicketResponse = TicketContext

__all__ = ["TicketResponse"]
