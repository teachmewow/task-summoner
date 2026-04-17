"""Failure analysis response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class FailureByPhase(BaseModel):
    phase: str
    count: int


class FailureByCategory(BaseModel):
    category: str
    count: int
    sample_message: str


class FailedTicket(BaseModel):
    ticket_key: str
    error: str
    category: str
    last_phase: str
    retry_count: int
    quarantined: bool
    updated_at: str
    total_cost_usd: float


class FailureSummaryResponse(BaseModel):
    total_failed: int
    quarantined: int
    healthy: int
    by_phase: list[FailureByPhase]
    by_category: list[FailureByCategory]
    tickets: list[FailedTicket]


class RetryResponse(BaseModel):
    ok: bool
    ticket_key: str
    new_state: str


__all__ = [
    "FailedTicket",
    "FailureByCategory",
    "FailureByPhase",
    "FailureSummaryResponse",
    "RetryResponse",
]
