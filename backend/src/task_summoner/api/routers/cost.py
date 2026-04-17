"""Cost & usage aggregation endpoints."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from task_summoner.api.deps import get_config_path, get_store
from task_summoner.api.schemas import (
    BudgetStatus,
    CostByDay,
    CostByProfile,
    CostByState,
    CostByTicket,
    CostSummaryResponse,
    TurnsBucket,
)
from task_summoner.config import TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.models import TicketContext

router = APIRouter(prefix="/api/cost", tags=["cost"])


@router.get("/summary", response_model=CostSummaryResponse)
async def cost_summary(
    request: Request,
    store: StateStore = Depends(get_store),
    config_path: Path = Depends(get_config_path),
) -> CostSummaryResponse:
    contexts = store.list_all()
    return _aggregate(contexts, _load_budget(config_path, request))


def _load_budget(config_path: Path, request: Request) -> float | None:
    """Prefer in-memory config (runtime state), fall back to re-reading YAML."""
    config = getattr(request.app.state, "config", None)
    if isinstance(config, TaskSummonerConfig):
        return config.monthly_budget_usd
    if not config_path.exists():
        return None
    try:
        return TaskSummonerConfig.load(config_path).monthly_budget_usd
    except Exception:
        return None


def _aggregate(contexts: list[TicketContext], budget: float | None) -> CostSummaryResponse:
    total_cost = 0.0
    run_count = 0
    profile_agg: dict[str, dict[str, float]] = defaultdict(
        lambda: {"cost_usd": 0.0, "turns": 0, "runs": 0},
    )
    state_agg: dict[str, dict[str, float]] = defaultdict(
        lambda: {"cost_usd": 0.0, "runs": 0},
    )
    day_agg: dict[str, float] = defaultdict(float)
    month_spent = 0.0
    now = datetime.now(UTC)
    current_month = now.strftime("%Y-%m")

    turns_buckets = [
        ("0-9", (0, 9)),
        ("10-49", (10, 49)),
        ("50-199", (50, 199)),
        ("200+", (200, 10**9)),
    ]
    turn_bucket_counts: dict[str, int] = {label: 0 for label, _ in turns_buckets}

    by_ticket: list[CostByTicket] = []

    for ctx in contexts:
        total_cost += ctx.total_cost_usd
        t_runs = len(ctx.cost_history)
        t_turns = sum(e.turns for e in ctx.cost_history)
        run_count += t_runs

        for entry in ctx.cost_history:
            profile_agg[entry.profile]["cost_usd"] += entry.cost_usd
            profile_agg[entry.profile]["turns"] += entry.turns
            profile_agg[entry.profile]["runs"] += 1
            state_agg[entry.state]["cost_usd"] += entry.cost_usd
            state_agg[entry.state]["runs"] += 1
            day = entry.timestamp[:10]
            day_agg[day] += entry.cost_usd
            if entry.timestamp.startswith(current_month):
                month_spent += entry.cost_usd
            for label, (lo, hi) in turns_buckets:
                if lo <= entry.turns <= hi:
                    turn_bucket_counts[label] += 1
                    break

        by_ticket.append(
            CostByTicket(
                ticket_key=ctx.ticket_key,
                cost_usd=round(ctx.total_cost_usd, 4),
                turns=t_turns,
                runs=t_runs,
                state=ctx.state.value,
                updated_at=ctx.updated_at,
            )
        )

    by_ticket.sort(key=lambda t: t.cost_usd, reverse=True)
    by_day = sorted(
        (CostByDay(date=day, cost_usd=round(cost, 4)) for day, cost in day_agg.items()),
        key=lambda d: d.date,
    )
    by_profile = sorted(
        (
            CostByProfile(
                profile=p,
                cost_usd=round(v["cost_usd"], 4),
                turns=int(v["turns"]),
                runs=int(v["runs"]),
            )
            for p, v in profile_agg.items()
        ),
        key=lambda p: p.cost_usd,
        reverse=True,
    )
    by_state = sorted(
        (
            CostByState(state=s, cost_usd=round(v["cost_usd"], 4), runs=int(v["runs"]))
            for s, v in state_agg.items()
        ),
        key=lambda s: s.cost_usd,
        reverse=True,
    )

    remaining = budget - month_spent if budget is not None else None
    pct = (month_spent / budget * 100) if budget else None

    ticket_count = len(contexts)
    avg = total_cost / ticket_count if ticket_count else 0.0

    return CostSummaryResponse(
        total_cost_usd=round(total_cost, 4),
        ticket_count=ticket_count,
        run_count=run_count,
        avg_per_ticket_usd=round(avg, 4),
        budget=BudgetStatus(
            monthly_budget_usd=budget,
            month_spent_usd=round(month_spent, 4),
            remaining_usd=round(remaining, 4) if remaining is not None else None,
            pct_used=round(pct, 2) if pct is not None else None,
        ),
        by_profile=by_profile,
        by_state=by_state,
        by_day=by_day,
        by_ticket=by_ticket,
        turns_histogram=[
            TurnsBucket(bucket=label, count=turn_bucket_counts[label]) for label, _ in turns_buckets
        ],
    )
