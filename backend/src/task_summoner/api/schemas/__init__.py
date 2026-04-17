"""Pydantic response models for the HTTP API.

Endpoint response shapes live here so they can be generated into TypeScript
types (the monorepo task, ENG-66, picks the codegen tool).

Where a response is just the persisted domain model, we re-export it from
`models/` rather than duplicating — e.g. `TicketContext` is both the on-disk
shape and the `/api/tickets/{key}` response.
"""

from task_summoner.api.schemas.config import (
    ConfigPayload,
    ConfigSaveResponse,
    ConfigStatus,
    ConfigTestResponse,
)
from task_summoner.api.schemas.cost import (
    BudgetStatus,
    CostByDay,
    CostByProfile,
    CostByState,
    CostByTicket,
    CostSummaryResponse,
    TurnsBucket,
)
from task_summoner.api.schemas.event import EventResponse
from task_summoner.api.schemas.ticket import TicketResponse

__all__ = [
    "BudgetStatus",
    "ConfigPayload",
    "ConfigSaveResponse",
    "ConfigStatus",
    "ConfigTestResponse",
    "CostByDay",
    "CostByProfile",
    "CostByState",
    "CostByTicket",
    "CostSummaryResponse",
    "EventResponse",
    "TicketResponse",
    "TurnsBucket",
]
