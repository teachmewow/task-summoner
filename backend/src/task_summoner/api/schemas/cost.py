"""Cost & usage response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class CostByProfile(BaseModel):
    profile: str
    cost_usd: float
    turns: int
    runs: int


class CostByState(BaseModel):
    state: str
    cost_usd: float
    runs: int


class CostByDay(BaseModel):
    date: str
    cost_usd: float


class CostByTicket(BaseModel):
    ticket_key: str
    cost_usd: float
    turns: int
    runs: int
    state: str
    updated_at: str


class TurnsBucket(BaseModel):
    bucket: str
    count: int


class BudgetStatus(BaseModel):
    monthly_budget_usd: float | None
    month_spent_usd: float
    remaining_usd: float | None
    pct_used: float | None


class CostSummaryResponse(BaseModel):
    total_cost_usd: float
    ticket_count: int
    run_count: int
    avg_per_ticket_usd: float
    budget: BudgetStatus
    by_profile: list[CostByProfile]
    by_state: list[CostByState]
    by_day: list[CostByDay]
    by_ticket: list[CostByTicket]
    turns_histogram: list[TurnsBucket]


__all__ = [
    "BudgetStatus",
    "CostByDay",
    "CostByProfile",
    "CostByState",
    "CostByTicket",
    "CostSummaryResponse",
    "TurnsBucket",
]
