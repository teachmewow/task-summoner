"""Failure analysis endpoints — FAILED ticket aggregation + requeue action."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException

from task_summoner.api.deps import get_store
from task_summoner.api.schemas import (
    FailedTicket,
    FailureByCategory,
    FailureByPhase,
    FailureSummaryResponse,
    RetryResponse,
)
from task_summoner.core import StateStore
from task_summoner.models import TicketContext, TicketState

router = APIRouter(prefix="/api/failures", tags=["failures"])

_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("board_not_found", ("not reachable on board", "not found on board")),
    ("timeout", ("timed out", "timeout")),
    ("budget_exhausted", ("budget exceeded", "max_budget", "max turns", "turn limit")),
    ("plugin", ("plugin",)),
    ("skill", ("skill tool", "skill(", "skill failed")),
    ("git", ("git ", "worktree", "branch", "conflict", "rebase")),
    ("network", ("connection", "network", "dns", "resolve")),
    ("auth", ("unauthori", "forbidden", "401", "403")),
]


def _categorize(error: str | None) -> str:
    if not error:
        return "unknown"
    low = error.lower()
    for name, needles in _CATEGORIES:
        if any(n in low for n in needles):
            return name
    return "other"


def _is_quarantined(ctx: TicketContext) -> bool:
    return bool(ctx.error and "not reachable on board" in ctx.error.lower())


def _last_phase(ctx: TicketContext) -> str:
    if ctx.cost_history:
        last = ctx.cost_history[-1]
        return last.state
    if ctx.state != TicketState.FAILED:
        return ctx.state.value
    return "UNKNOWN"


@router.get("/summary", response_model=FailureSummaryResponse)
async def failure_summary(store: StateStore = Depends(get_store)) -> FailureSummaryResponse:
    contexts = store.list_all()
    failed = [c for c in contexts if c.state == TicketState.FAILED]
    healthy = len(contexts) - len(failed)
    quarantined = sum(1 for c in failed if _is_quarantined(c))

    phase_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)
    category_samples: dict[str, str] = {}

    tickets: list[FailedTicket] = []
    for ctx in failed:
        phase = _last_phase(ctx)
        category = _categorize(ctx.error)
        phase_counts[phase] += 1
        category_counts[category] += 1
        if category not in category_samples and ctx.error:
            category_samples[category] = ctx.error[:140]
        tickets.append(
            FailedTicket(
                ticket_key=ctx.ticket_key,
                error=ctx.error or "",
                category=category,
                last_phase=phase,
                retry_count=ctx.retry_count,
                quarantined=_is_quarantined(ctx),
                updated_at=ctx.updated_at,
                total_cost_usd=round(ctx.total_cost_usd, 4),
            )
        )

    tickets.sort(key=lambda t: t.updated_at, reverse=True)

    by_phase = sorted(
        (FailureByPhase(phase=p, count=c) for p, c in phase_counts.items()),
        key=lambda x: x.count,
        reverse=True,
    )
    by_category = sorted(
        (
            FailureByCategory(category=cat, count=cnt, sample_message=category_samples.get(cat, ""))
            for cat, cnt in category_counts.items()
        ),
        key=lambda x: x.count,
        reverse=True,
    )

    return FailureSummaryResponse(
        total_failed=len(failed),
        quarantined=quarantined,
        healthy=healthy,
        by_phase=by_phase,
        by_category=by_category,
        tickets=tickets,
    )


@router.post("/{ticket_key}/retry", response_model=RetryResponse)
async def retry_ticket(ticket_key: str, store: StateStore = Depends(get_store)) -> RetryResponse:
    ctx = store.load(ticket_key)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_key} not found")
    if ctx.state != TicketState.FAILED:
        raise HTTPException(
            status_code=400,
            detail=f"Ticket is not in FAILED state (current: {ctx.state.value})",
        )
    ctx.state = TicketState.QUEUED
    ctx.error = None
    ctx.retry_count = 0
    store.save(ctx)
    return RetryResponse(ok=True, ticket_key=ticket_key, new_state=ctx.state.value)
