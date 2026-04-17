"""Per-run cost record — appended to TicketContext.cost_history on each agent run."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class CostEntry(BaseModel):
    """One agent run's contribution to a ticket's cost."""

    timestamp: str = Field(default_factory=_now_iso)
    cost_usd: float = Field(default=0.0, ge=0.0)
    turns: int = Field(default=0, ge=0)
    profile: str = "unknown"
    state: str = "unknown"
